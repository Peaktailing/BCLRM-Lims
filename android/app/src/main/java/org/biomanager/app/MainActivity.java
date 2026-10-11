package org.biomanager.app;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.Rect;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.PopupMenu;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONException;
import org.json.JSONObject;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import com.google.mlkit.vision.codescanner.GmsBarcodeScanner;
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning;

/**
 * The lab server's BioManager, full screen. Links to the server stay in the
 * app; anything else opens in the browser. A Scan button reads a cage card's
 * QR code and opens the record it points to.
 */
public class MainActivity extends Activity {
    private static final int PICK_FILE = 1;
    /** The offline screens the app carries (app/static/offline/, copied into the assets). */
    private static final String OFFLINE = "file:///android_asset/offline/";
    private static final long REFRESH_EVERY = 15 * 60 * 1000L;

    private OfflineStore store;
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final Handler ticker = new Handler(Looper.getMainLooper());
    private final Runnable refresh = new Runnable() {
        @Override
        public void run() {
            io.execute(() -> store.sync());
            ticker.postDelayed(this, REFRESH_EVERY);
        }
    };
    /** The page now showing, for the bridges (asked from other threads). */
    private volatile String currentUrl = "";

    private String server;
    private WebView web;
    private ProgressBar progress;
    private View offline;
    private TextView offlineDetail;
    private ValueCallback<Uri[]> pendingFiles;
    private View scanButton;
    /** The page shows a Scan button of its own (its phone tab bar), so the app's stays hidden. */
    private boolean pageHasScan;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        server = Server.get(this);
        if (server == null) {
            startActivity(new Intent(this, SetupActivity.class)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK));
            finish();
            return;
        }
        store = OfflineStore.get(this);
        setContentView(R.layout.activity_main);
        web = findViewById(R.id.web);
        progress = findViewById(R.id.progress);
        offline = findViewById(R.id.offline);
        offlineDetail = findViewById(R.id.offline_detail);

        findViewById(R.id.retry).setOnClickListener(v -> {
            offline.setVisibility(View.GONE);
            web.reload();
        });
        findViewById(R.id.change_server).setOnClickListener(v -> changeServer());
        scanButton = findViewById(R.id.scan);
        scanButton.setOnClickListener(v -> scan(false));
        // Before walking into a facility with no signal: a fresh copy, or its screens now.
        scanButton.setOnLongClickListener(v -> {
            PopupMenu menu = new PopupMenu(this, v);
            menu.getMenu().add(0, 1, 0, R.string.get_ready);
            menu.getMenu().add(0, 2, 1, R.string.work_offline);
            menu.setOnMenuItemClickListener(item -> {
                if (item.getItemId() == 1) getReady(); else if (!openOffline()) toast(R.string.no_copy);
                return true;
            });
            menu.show();
            return true;
        });
        hideWhileTyping(scanButton);
        // Catch up whenever the network comes back.
        ConnectivityManager net = getSystemService(ConnectivityManager.class);
        if (net != null) {
            net.registerDefaultNetworkCallback(new ConnectivityManager.NetworkCallback() {
                @Override
                public void onAvailable(Network network) {
                    io.execute(() -> store.sync());
                }
            });
        }

        configure(web);
        if (savedInstanceState != null) {
            web.restoreState(savedInstanceState);
        } else {
            web.loadUrl(server + "/");
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void configure(WebView view) {
        WebSettings settings = view.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);  // tabs and preferences live in localStorage
        settings.setUserAgentString(settings.getUserAgentString() + " BioManagerAndroid/" + BuildConfigVersion.name(this));
        view.addJavascriptInterface(new PageBridge(), "BioManagerApp");
        view.addJavascriptInterface(new StoreBridge(), "BMNative");

        CookieManager cookies = CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        cookies.setAcceptThirdPartyCookies(view, false);

        view.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest request) {
                Uri link = request.getUrl();
                if (Server.owns(server, link) || link.toString().startsWith(OFFLINE)) return false;
                openElsewhere(link);
                return true;
            }

            @Override
            public void onPageStarted(WebView v, String url, Bitmap favicon) {
                currentUrl = url == null ? "" : url;
                progress.setVisibility(View.VISIBLE);
                // Each page says again whether it has its own Scan.
                pageHasScan = false;
                scanButton.setVisibility(View.VISIBLE);
            }

            @Override
            public void onPageFinished(WebView v, String url) {
                progress.setVisibility(View.GONE);
                // Signed in through the page: this phone gets its own device token to sync with.
                if (url != null && Server.owns(server, Uri.parse(url)) && store.token() == null) {
                    String cookie = CookieManager.getInstance().getCookie(server);
                    String agent = v.getSettings().getUserAgentString();
                    io.execute(() -> store.registerIfNeeded(cookie, agent));
                }
            }

            @Override
            public void onReceivedError(WebView v, WebResourceRequest request, WebResourceError error) {
                if (!request.isForMainFrame()) return;
                if (unreachable(error.getErrorCode())) {
                    // With a copy of the facility, the offline screens; without, "can't reach".
                    if (openOffline()) return;
                    offlineDetail.setText(getString(R.string.err_unreachable, server));
                    offline.setVisibility(View.VISIBLE);
                } else {
                    // Not a network problem: most often Back to a page that was the answer to a
                    // form (it cannot be shown again without resending). Start over at home.
                    v.loadUrl(server + "/");
                }
            }
        });

        view.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView v, int percent) {
                progress.setProgress(percent);
            }

            // Photos and files for the notebook and records.
            @Override
            public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (pendingFiles != null) pendingFiles.onReceiveValue(null);
                pendingFiles = callback;
                try {
                    startActivityForResult(params.createIntent(), PICK_FILE);
                } catch (ActivityNotFoundException e) {
                    pendingFiles = null;
                    return false;
                }
                return true;
            }
        });

        // CSV exports, printed sheets and backups: hand them to the system's downloader,
        // with this session's cookie so the server knows who is asking.
        view.setDownloadListener((url, userAgent, disposition, mimeType, length) -> {
            String name = URLUtil.guessFileName(url, disposition, mimeType);
            DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url))
                    .addRequestHeader("Cookie", CookieManager.getInstance().getCookie(url))
                    .addRequestHeader("User-Agent", userAgent)
                    .setMimeType(mimeType)
                    .setTitle(name)
                    .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                    .setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name);
            DownloadManager downloads = getSystemService(DownloadManager.class);
            if (downloads != null) {
                downloads.enqueue(request);
                Toast.makeText(this, getString(R.string.downloading, name), Toast.LENGTH_SHORT).show();
            }
        });
    }

    /** The Scan button would cover form fields while the keyboard is up. */
    private void hideWhileTyping(View button) {
        View root = findViewById(android.R.id.content);
        root.getViewTreeObserver().addOnGlobalLayoutListener(() -> {
            boolean typing;
            WindowInsets insets = root.getRootWindowInsets();
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R && insets != null) {
                typing = insets.isVisible(WindowInsets.Type.ime());
            } else {
                Rect visible = new Rect();
                root.getWindowVisibleDisplayFrame(visible);
                typing = visible.height() < root.getRootView().getHeight() * 0.75;
            }
            button.setVisibility(typing || pageHasScan ? View.GONE : View.VISIBLE);
        });
    }

    /**
     * What the lab server's pages may ask of the app (window.BioManagerApp). A page
     * with the phone tab bar has its own Scan: it hides the app's button and asks
     * for the scanner from there. Only the server's own pages are answered.
     */
    private final class PageBridge {
        @JavascriptInterface
        public void pageHasScan() {
            runOnUiThread(() -> {
                if (!fromServer()) return;
                pageHasScan = true;
                scanButton.setVisibility(View.GONE);
            });
        }

        @JavascriptInterface
        public void scan() {
            runOnUiThread(() -> {
                if (fromServer()) MainActivity.this.scan(true);
            });
        }

        private boolean fromServer() {
            String url = web.getUrl();
            return url != null && Server.owns(server, Uri.parse(url));
        }
    }

    /**
     * What the offline screens ask of this phone's copy (window.BMNative.post),
     * answered with window.BMStoreReply. Only the screens the app carries are answered.
     */
    private final class StoreBridge {
        @JavascriptInterface
        public void post(String message) {
            if (!currentUrl.startsWith(OFFLINE)) return;
            io.execute(() -> answer(message));
        }

        private void answer(String message) {
            int id = -1;
            boolean ok = true;
            JSONObject value = new JSONObject();
            try {
                JSONObject call = new JSONObject(message);
                id = call.getInt("id");
                switch (call.optString("name")) {
                    case "load":
                        JSONObject snap = store.snapshot();
                        value.put("snapshot", snap == null ? JSONObject.NULL : snap).put("queue", store.queue())
                                .put("status", store.status());
                        break;
                    case "add":
                        value.put("ok", true).put("waiting", store.add(call.getJSONObject("arg")));
                        break;
                    case "sync":
                        value.put("ok", true).put("status", store.sync());
                        break;
                    case "status":
                        value.put("online", store.reachable()).put("store", store.status());
                        break;
                    case "strings":
                        value = store.strings();
                        break;
                    case "online":
                        runOnUiThread(() -> web.loadUrl(server + "/"));
                        break;
                    default:
                        ok = false;
                        value.put("error", "unknown call");
                }
            } catch (JSONException e) {
                ok = false;
                try {
                    value = new JSONObject().put("error", String.valueOf(e.getMessage()));
                } catch (JSONException ignored) {
                    value = new JSONObject();
                }
            }
            if (id < 0) return;
            String script = "window.BMStoreReply(" + id + ", " + ok + ", " + value + ")";
            runOnUiThread(() -> web.evaluateJavascript(script, null));
        }
    }

    /** The offline screens, on this phone's copy. False when there is no copy yet. */
    private boolean openOffline() {
        if (!store.hasCopy()) return false;
        offline.setVisibility(View.GONE);
        web.loadUrl(OFFLINE + "index.html");
        return true;
    }

    private void getReady() {
        io.execute(() -> {
            JSONObject status = store.sync();
            boolean ready = status.optBoolean("has_copy") && status.optBoolean("online");
            String error = status.optString("error", "");
            runOnUiThread(() -> {
                if (ready) toast(R.string.ready);
                else if (!error.isEmpty()) Toast.makeText(this, error, Toast.LENGTH_LONG).show();
                else toast(R.string.no_copy);
            });
        });
    }

    private void toast(int text) {
        Toast.makeText(this, text, Toast.LENGTH_LONG).show();
    }

    /** Errors that mean the server could not be reached at all. */
    private static boolean unreachable(int code) {
        return code == WebViewClient.ERROR_HOST_LOOKUP || code == WebViewClient.ERROR_CONNECT
                || code == WebViewClient.ERROR_TIMEOUT || code == WebViewClient.ERROR_IO
                || code == WebViewClient.ERROR_FAILED_SSL_HANDSHAKE || code == WebViewClient.ERROR_PROXY_AUTHENTICATION;
    }

    /**
     * Read a cage card. A page that asked for the scanner (bench mode), and the
     * offline screens, get what was read (window.bmScanned), as on the iPhone;
     * otherwise the record its QR code points to opens.
     */
    private void scan(boolean forPage) {
        GmsBarcodeScanner scanner = GmsBarcodeScanning.getClient(this);
        scanner.startScan()
                .addOnSuccessListener(barcode -> {
                    String value = barcode.getRawValue();
                    if (value != null && (forPage || currentUrl.startsWith(OFFLINE))) {
                        web.evaluateJavascript("window.bmScanned && window.bmScanned(" + JSONObject.quote(value) + ")", null);
                        return;
                    }
                    Uri link = value == null ? null : Uri.parse(value.trim());
                    if (link != null && Server.owns(server, link)) {
                        offline.setVisibility(View.GONE);
                        web.loadUrl(link.toString());
                    } else if (link != null && link.getHost() != null) {
                        Toast.makeText(this, getString(R.string.scan_other_server, link.getHost()), Toast.LENGTH_LONG).show();
                    } else {
                        Toast.makeText(this, R.string.scan_not_link, Toast.LENGTH_SHORT).show();
                    }
                })
                .addOnFailureListener(e ->
                        Toast.makeText(this, R.string.scan_unavailable, Toast.LENGTH_LONG).show());
    }

    private void openElsewhere(Uri link) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, link));
        } catch (ActivityNotFoundException ignored) {
            // Nothing on the phone opens it; stay where we are.
        }
    }

    private void changeServer() {
        startActivity(new Intent(this, SetupActivity.class));
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == PICK_FILE && pendingFiles != null) {
            pendingFiles.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode, data));
            pendingFiles = null;
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        // Back from Change server with a new address: open it.
        String saved = Server.get(this);
        if (saved != null && !saved.equals(server)) {
            server = saved;
            web.clearHistory();
            web.loadUrl(server + "/");
        }
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (web != null && web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        if (web != null) web.saveState(outState);
    }

    @Override
    protected void onResume() {
        super.onResume();
        // This phone's copy of the facility stays fresh while the app is open.
        if (store != null) {
            ticker.removeCallbacks(refresh);
            ticker.post(refresh);
        }
    }

    @Override
    protected void onPause() {
        CookieManager.getInstance().flush();  // stay signed in after the app is closed
        ticker.removeCallbacks(refresh);
        super.onPause();
    }
}
