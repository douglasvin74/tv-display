package br.com.multilaser.tvdisplay;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.text.InputType;
import android.view.KeyEvent;
import android.widget.EditText;
import android.graphics.Color;
import android.os.Bundle;
import android.view.View;
import android.view.WindowManager;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

public class MainActivity extends Activity {
    // IP do notebook (server.py), guardado no app. Se mudar de rede, o app pergunta o novo.
    private static final String DEFAULT_IP = "192.168.246.100";

    private WebView web;
    private SharedPreferences prefs;
    private int falhas;
    private boolean dialogo, carregou, erro;

    private String url() {
        return "http://" + prefs.getString("ip", DEFAULT_IP) + ":8000/tv";
    }

    private String versao() {
        try {
            return getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
        } catch (Exception e) {
            return "?";
        }
    }

    private void perguntaIp() {
        if (dialogo) return;
        dialogo = true;
        EditText in = new EditText(this);
        in.setInputType(InputType.TYPE_CLASS_PHONE);
        in.setText(prefs.getString("ip", DEFAULT_IP));
        new AlertDialog.Builder(this)
                .setTitle("TV Display v" + versao() + " - IP do notebook")
                .setView(in)
                .setPositiveButton("Conectar", (d, w) -> {
                    prefs.edit().putString("ip", in.getText().toString().trim()).apply();
                    falhas = 0;
                    erro = false;
                    web.loadUrl(url());
                })
                .setNegativeButton("Cancelar", null)
                .setOnDismissListener(d -> dialogo = false)
                .show();
    }

    @Override
    public boolean onKeyDown(int code, KeyEvent e) {
        if (code == KeyEvent.KEYCODE_MENU || (!carregou && code == KeyEvent.KEYCODE_DPAD_CENTER)) {
            perguntaIp();
            return true;
        }
        return super.onKeyDown(code, e);
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences("tv", MODE_PRIVATE);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        web = new WebView(this);
        web.setBackgroundColor(Color.BLACK);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView v, String u) {
                if (!erro) carregou = true;
            }

            @Override
            public void onReceivedError(WebView v, WebResourceRequest r, WebResourceError e) {
                if (!r.isForMainFrame()) return;
                erro = true;
                if (++falhas == 3) perguntaIp();
                v.postDelayed(() -> { erro = false; v.loadUrl(url()); }, 5000);
            }
        });
        setContentView(web);
        web.loadUrl(url());
        // Servidor inalcançável (outra rede) pode demorar minutos para dar erro: pergunta o IP antes.
        web.postDelayed(() -> { if (!carregou) perguntaIp(); }, 8000);
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            getWindow().getDecorView().setSystemUiVisibility(
                    View.SYSTEM_UI_FLAG_FULLSCREEN | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                            | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY | View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
        }
    }

    @Override
    protected void onDestroy() {
        web.destroy();
        super.onDestroy();
    }
}
