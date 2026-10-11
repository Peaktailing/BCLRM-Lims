package org.biomanager.app;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TimeZone;

/**
 * This phone's copy of the facility, for working where there is no signal
 * (the server's side is app/sync.py).
 *
 * While the lab's server answers, the app keeps what its person needs (the
 * server's snapshot) and catches up from the change feed: when the app comes
 * forward, when the network comes back and every 15 minutes while it is open.
 * When the server can't be reached, the web view shows the offline screens the
 * app carries (app/static/offline/, in the assets), which read this copy and
 * add what is done to a queue; the queue goes to the lab, in order, as soon as
 * it answers again.
 *
 * The phone signs in to sync as one of its person's devices: once they are
 * signed in through the app's page, it asks the server for a device token of
 * its own (POST /api/devices/this-app). Everything is in the app's private
 * storage, which Android encrypts.
 */
final class OfflineStore {
    private static final String PREFS = "biomanager-offline";
    private static final Set<String> FINISHED = new HashSet<>(java.util.Arrays.asList("applied", "merged", "held", "refused"));
    private static final Map<String, String> TABLES = new HashMap<>();
    static {
        TABLES.put("mice", "mice");
        TABLES.put("mouse_cages", "cages");
        TABLES.put("litters", "litters");
        TABLES.put("mouse_weights", "weights");
        TABLES.put("tasks", "tasks");
        TABLES.put("mouse_racks", "racks");
        TABLES.put("stock_units", "stock_units");
        TABLES.put("tanks", "tanks");
    }

    private static OfflineStore instance;
    private final Context context;
    private boolean syncing;
    private long nextRegistration;

    static synchronized OfflineStore get(Context context) {
        if (instance == null) instance = new OfflineStore(context.getApplicationContext());
        return instance;
    }

    private OfflineStore(Context context) {
        this.context = context;
    }

    // ------------------------------------------------------------ where it lives
    private String server() {
        return Server.get(context);
    }

    private String key() {
        String server = server();
        return server == null ? "lab" : Integer.toHexString(server.hashCode());
    }

    private File folder() {
        return new File(new File(context.getFilesDir(), "offline"), key());
    }

    private SharedPreferences prefs() {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    String token() {
        return prefs().getString("token-" + key(), null);
    }

    private void setToken(String token, String device) {
        SharedPreferences.Editor edit = prefs().edit();
        if (token == null) edit.remove("token-" + key()); else edit.putString("token-" + key(), token);
        if (device != null) edit.putString("device-" + key(), device);
        edit.apply();
    }

    private synchronized Object read(String name) {
        File file = new File(folder(), name + ".json");
        if (!file.isFile()) return null;
        try (InputStream in = new FileInputStream(file)) {
            String text = new String(readAll(in), StandardCharsets.UTF_8);
            return text.trim().startsWith("[") ? new JSONArray(text) : new JSONObject(text);
        } catch (IOException | JSONException e) {
            return null;
        }
    }

    private synchronized void write(String name, Object value) {
        File dir = folder();
        if (!dir.isDirectory() && !dir.mkdirs()) return;
        File part = new File(dir, name + ".part");
        try (OutputStream out = new FileOutputStream(part)) {
            out.write(value.toString().getBytes(StandardCharsets.UTF_8));
        } catch (IOException e) {
            return;
        }
        //noinspection ResultOfMethodCallIgnored
        part.renameTo(new File(dir, name + ".json"));
    }

    JSONObject snapshot() {
        Object value = read("snapshot");
        return value instanceof JSONObject ? (JSONObject) value : null;
    }

    JSONArray queue() {
        Object value = read("queue");
        return value instanceof JSONArray ? (JSONArray) value : new JSONArray();
    }

    private JSONObject state() {
        Object value = read("state");
        return value instanceof JSONObject ? (JSONObject) value : new JSONObject();
    }

    private void setState(String name, Object value) throws JSONException {
        JSONObject state = state();
        state.put(name, value);
        write("state", state);
    }

    boolean hasCopy() {
        return snapshot() != null;
    }

    // ------------------------------------------------------------ what the screens do
    synchronized int add(JSONObject op) throws JSONException {
        String id = op.optString("op", "");
        if (id.isEmpty() || op.optString("action", "").isEmpty()) throw new JSONException("a change is {op, action, …}");
        JSONArray queue = queue();
        for (int i = 0; i < queue.length(); i++) {
            if (id.equals(queue.getJSONObject(i).optString("op"))) return queue.length();
        }
        queue.put(op);
        write("queue", queue);
        return queue.length();
    }

    JSONObject status() throws JSONException {
        JSONObject snap = snapshot();
        JSONObject state = state();
        return new JSONObject()
                .put("waiting", queue().length())
                .put("taken", snap == null ? "" : snap.optString("taken", ""))
                .put("cursor", snap == null ? JSONObject.NULL : snap.opt("cursor"))
                .put("has_copy", snap != null)
                .put("last_sync", state.optString("last_sync", ""))
                .put("error", state.optString("error", ""))
                .put("held", state.optInt("held", 0))
                .put("refused", state.optJSONArray("refused") == null ? new JSONArray() : state.optJSONArray("refused"))
                .put("online", state.optBoolean("online", false));
    }

    /** The bundle's words in the phone's language (assets/js-offline.json). */
    JSONObject strings() throws JSONException {
        boolean zh = Locale.getDefault().getLanguage().equals("zh");
        JSONObject out = new JSONObject().put("lang", zh ? "zh" : "en").put("words", new JSONObject());
        if (!zh) return out;
        try (InputStream in = context.getAssets().open("js-offline.json")) {
            out.put("words", new JSONObject(new String(readAll(in), StandardCharsets.UTF_8)));
        } catch (IOException ignored) {
            // English, then
        }
        return out;
    }

    // ------------------------------------------------------------ talking to the server
    private JSONObject call(String method, String path, JSONObject body, int timeoutSeconds) throws IOException, JSONException {
        String token = token();
        if (token == null || server() == null) throw new IOException("This phone hasn't signed in to sync yet.");
        HttpURLConnection http = (HttpURLConnection) new URL(server() + path).openConnection();
        http.setRequestMethod(method);
        http.setConnectTimeout(15000);
        http.setReadTimeout(timeoutSeconds * 1000);
        http.setRequestProperty("Authorization", "Bearer " + token);
        http.setRequestProperty("Accept", "application/json");
        http.setRequestProperty("Content-Type", "application/json");
        http.setRequestProperty("X-BioManager-Version", BuildConfigVersion.name(context));
        if (body != null) {
            http.setDoOutput(true);
            try (OutputStream out = http.getOutputStream()) {
                out.write(body.toString().getBytes(StandardCharsets.UTF_8));
            }
        }
        int code = http.getResponseCode();
        if (code == 401) {
            setToken(null, null);
            throw new IOException("This phone was signed out of the lab.");
        }
        if (code < 200 || code >= 300) throw new IOException("The server answered " + code + ".");
        try (InputStream in = http.getInputStream()) {
            return new JSONObject(new String(readAll(in), StandardCharsets.UTF_8));
        } finally {
            http.disconnect();
        }
    }

    /** Whether the lab's server answers just now. */
    boolean reachable() {
        if (server() == null) return false;
        try {
            HttpURLConnection http = (HttpURLConnection) new URL(server() + "/healthz").openConnection();
            http.setConnectTimeout(6000);
            http.setReadTimeout(6000);
            try (InputStream in = http.getInputStream()) {
                return http.getResponseCode() == 200 && new String(readAll(in), StandardCharsets.UTF_8).trim().equals("ok");
            } finally {
                http.disconnect();
            }
        } catch (IOException e) {
            return false;
        }
    }

    /** Send what waits, in order; then catch up with the lab. Call off the main thread. */
    JSONObject sync() {
        synchronized (this) {
            if (syncing || token() == null) return statusOrEmpty();
            syncing = true;
        }
        try {
            push();
            catchUp();
            setState("online", true);
            setState("error", "");
            setState("last_sync", now());
        } catch (IOException | JSONException e) {
            try {
                setState("online", false);
                setState("error", String.valueOf(e.getMessage()));
            } catch (JSONException ignored) {
                // nothing more to say
            }
        } finally {
            synchronized (this) {
                syncing = false;
            }
        }
        return statusOrEmpty();
    }

    private JSONObject statusOrEmpty() {
        try {
            return status();
        } catch (JSONException e) {
            return new JSONObject();
        }
    }

    private void push() throws IOException, JSONException {
        JSONArray waiting = queue();
        if (waiting.length() == 0) return;
        JSONArray sent = new JSONArray();
        for (int i = 0; i < Math.min(200, waiting.length()); i++) sent.put(waiting.get(i));
        JSONObject answer = call("POST", "/api/sync/push", new JSONObject().put("ops", sent), 300);
        JSONArray results = answer.optJSONArray("results");
        Set<String> done = new HashSet<>();
        JSONObject ids = new JSONObject();
        JSONArray refused = state().optJSONArray("refused");
        if (refused == null) refused = new JSONArray();
        for (int i = 0; results != null && i < results.length(); i++) {
            JSONObject r = results.getJSONObject(i);
            String result = r.optString("result");
            if (FINISHED.contains(result)) done.add(r.optString("op"));
            if ("refused".equals(result)) refused.put(new JSONObject().put("op", r.optString("op")).put("message", r.optString("message")));
            JSONObject made = r.optJSONObject("ids");
            if (made != null) {
                for (Iterator<String> it = made.keys(); it.hasNext(); ) {
                    String tmp = it.next();
                    ids.put(tmp, made.get(tmp));
                }
            }
        }
        synchronized (this) {
            JSONArray current = queue(), remaining = new JSONArray();
            for (int i = 0; i < current.length(); i++) {
                JSONObject op = current.getJSONObject(i);
                // Later changes naming what an applied one made now name the real record.
                if (!done.contains(op.optString("op"))) remaining.put(rename(op, ids));
            }
            write("queue", remaining);
        }
        JSONArray kept = new JSONArray();
        for (int i = Math.max(0, refused.length() - 50); i < refused.length(); i++) kept.put(refused.get(i));
        setState("refused", kept);
        setState("held", answer.optInt("held", 0));
    }

    private static Object rename(Object value, JSONObject ids) throws JSONException {
        if (value instanceof String && ids.has((String) value)) return ids.get((String) value);
        if (value instanceof JSONArray) {
            JSONArray list = (JSONArray) value, out = new JSONArray();
            for (int i = 0; i < list.length(); i++) out.put(rename(list.get(i), ids));
            return out;
        }
        if (value instanceof JSONObject) {
            JSONObject map = (JSONObject) value, out = new JSONObject();
            for (Iterator<String> it = map.keys(); it.hasNext(); ) {
                String k = it.next();
                out.put(k, rename(map.get(k), ids));
            }
            return out;
        }
        return value;
    }

    private void catchUp() throws IOException, JSONException {
        JSONObject snap = snapshot();
        if (snap != null && snap.opt("cursor") instanceof Integer) {
            int cursor = snap.getInt("cursor");
            JSONObject answer = call("GET", "/api/sync/changes?since=" + cursor, null, 60);
            if (!answer.optBoolean("reset", false)) {
                JSONObject changes = answer.optJSONObject("changes");
                for (Iterator<String> it = changes == null ? java.util.Collections.<String>emptyIterator() : changes.keys(); it.hasNext(); ) {
                    String name = it.next();
                    LinkedHashMap<Integer, JSONObject> rows = new LinkedHashMap<>();
                    JSONArray had = snap.optJSONArray(name);
                    for (int i = 0; had != null && i < had.length(); i++) rows.put(had.getJSONObject(i).getInt("id"), had.getJSONObject(i));
                    JSONArray came = changes.getJSONArray(name);
                    for (int i = 0; i < came.length(); i++) rows.put(came.getJSONObject(i).getInt("id"), came.getJSONObject(i));
                    snap.put(name, new JSONArray(rows.values()));
                }
                JSONArray gone = answer.optJSONArray("gone");
                for (int i = 0; gone != null && i < gone.length(); i++) {
                    JSONObject g = gone.getJSONObject(i);
                    String name = TABLES.get(g.optString("table"));
                    JSONArray had = name == null ? null : snap.optJSONArray(name);
                    if (had == null) continue;
                    JSONArray kept = new JSONArray();
                    for (int j = 0; j < had.length(); j++) {
                        if (had.getJSONObject(j).optInt("id", -1) != g.optInt("id", -2)) kept.put(had.get(j));
                    }
                    snap.put(name, kept);
                }
                snap.put("cursor", answer.optInt("cursor", cursor));
                snap.put("taken", now());
                write("snapshot", snap);
                return;
            }
        }
        JSONObject fresh = call("GET", "/api/sync/snapshot", null, 300);
        if (fresh.optBoolean("ok", false)) write("snapshot", fresh);
    }

    // ------------------------------------------------------------ signing in to sync
    /**
     * Once its person is signed in through the app's page, the phone asks for a
     * device token of its own, with the page's sign-in (its cookie). Off the main thread.
     */
    void registerIfNeeded(String cookie, String userAgent) {
        String server = server();
        if (token() != null || server == null || cookie == null || cookie.isEmpty()) return;
        if (System.currentTimeMillis() < nextRegistration) return;
        nextRegistration = System.currentTimeMillis() + 60_000;
        try {
            HttpURLConnection http = (HttpURLConnection) new URL(server + "/api/devices/this-app").openConnection();
            http.setRequestMethod("POST");
            http.setConnectTimeout(15000);
            http.setReadTimeout(30000);
            http.setDoOutput(true);
            http.setRequestProperty("Cookie", cookie);
            http.setRequestProperty("User-Agent", userAgent);
            http.setRequestProperty("Origin", server);
            http.setRequestProperty("Content-Type", "application/json");
            JSONObject body = new JSONObject().put("name", Build.MANUFACTURER + " " + Build.MODEL).put("platform", "android")
                    .put("app_version", BuildConfigVersion.name(context));
            String before = prefs().getString("device-" + key(), null);
            if (before != null) body.put("replaces", before);
            try (OutputStream out = http.getOutputStream()) {
                out.write(body.toString().getBytes(StandardCharsets.UTF_8));
            }
            if (http.getResponseCode() != 200) return;
            JSONObject answer;
            try (InputStream in = http.getInputStream()) {
                answer = new JSONObject(new String(readAll(in), StandardCharsets.UTF_8));
            }
            setToken(answer.getString("token"), answer.optString("device", null));
            sync();
        } catch (IOException | JSONException ignored) {
            // Not signed in yet, or no signal: asked again on a later page.
        }
    }

    // ------------------------------------------------------------ helpers
    private static String now() {
        SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.ROOT);
        format.setTimeZone(TimeZone.getTimeZone("UTC"));
        return format.format(new Date());
    }

    private static byte[] readAll(InputStream in) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[16384];
        int n;
        while ((n = in.read(buffer)) > 0) out.write(buffer, 0, n);
        return out.toByteArray();
    }
}
