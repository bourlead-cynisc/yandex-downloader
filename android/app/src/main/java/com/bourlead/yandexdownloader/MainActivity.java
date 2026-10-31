package com.bourlead.yandexdownloader;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.ClipData;
import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.provider.DocumentsContract;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;
import android.widget.Toast;

import androidx.documentfile.provider.DocumentFile;

import com.chaquo.python.Python;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private static final int PICK_FOLDER = 210;
    private static final int BG = Color.rgb(16, 17, 20);
    private static final int PANEL = Color.rgb(26, 28, 32);
    private static final int FIELD = Color.rgb(35, 38, 44);
    private static final int ACCENT = Color.rgb(255, 204, 50);
    private static final int FG = Color.rgb(242, 243, 245);
    private static final int MUTED = Color.rgb(153, 159, 169);
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private EditText urlInput;
    private EditText tokenInput;
    private TextView folderText;
    private TextView authText;
    private TextView statusText;
    private TextView detailText;
    private TextView speedText;
    private TextView logText;
    private Button authButton;
    private Button tokenButton;
    private Button folderButton;
    private Button startButton;
    private Button cancelButton;
    private CheckBox subfolderCheck;
    private Spinner qualitySpinner;
    private ProgressBar overallBar;
    private ProgressBar trackBar;
    private Uri folderUri;
    private DocumentFile currentDestination;
    private String currentCacheDir;
    private boolean busy = false;
    private boolean authBusy = false;
    private boolean loggedIn = false;

    public class BridgeListener {
        public void onEvent(String kind, String dataJson) {
            try {
                JSONObject data = new JSONObject(dataJson);
                if ("resolved".equals(kind)) {
                    if (currentDestination == null) throw new IllegalStateException("Папка недоступна");
                    if (subfolderCheck.isChecked()) {
                        String title = sanitized(data.optString("title", "Плейлист"));
                        if (!"Один трек".equals(data.optString("title"))) {
                            DocumentFile dir = currentDestination.findFile(title);
                            if (dir == null) dir = currentDestination.createDirectory(title);
                            if (dir == null || !dir.isDirectory()) throw new IllegalStateException("Не удалось создать папку для плейлиста");
                            currentDestination = dir;
                        }
                    }
                }
                if ("saved".equals(kind)) {
                    String fileName = sanitized(data.getString("name"));
                    File source = new File(currentCacheDir, fileName);
                    copyToSelectedDirectory(source);
                }
                runOnUiThread(() -> displayEvent(kind, data));
            } catch (Exception ex) {
                // Propagate failures to download_all so it reports the affected track.
                throw new IllegalStateException("Ошибка сохранения в Android: " + ex.getMessage(), ex);
            }
        }
    }
    private final BridgeListener listener = new BridgeListener();

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        buildScreen();
        String saved = getPreferences(MODE_PRIVATE).getString("folder_uri", null);
        if (saved != null) {
            folderUri = Uri.parse(saved);
            folderText.setText(folderUri.getLastPathSegment());
        }
        acceptSharedUrl(getIntent());
    }

    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        acceptSharedUrl(intent);
    }

    private void acceptSharedUrl(Intent intent) {
        if (Intent.ACTION_SEND.equals(intent.getAction()) && "text/plain".equals(intent.getType())) {
            String value = intent.getStringExtra(Intent.EXTRA_TEXT);
            if (value != null) {
                java.util.regex.Matcher m = java.util.regex.Pattern.compile("https?://music\\.yandex\\.(?:ru|com|kz|by)/[^\\s]+", java.util.regex.Pattern.CASE_INSENSITIVE).matcher(value);
                if (m.find()) urlInput.setText(m.group());
            }
        }
    }

    private int dp(float v) { return (int) (getResources().getDisplayMetrics().density * v + 0.5f); }

    private GradientDrawable rounded(int background, int radius) {
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(background);
        shape.setCornerRadius(dp(radius));
        return shape;
    }

    private LinearLayout vertical() {
        LinearLayout result = new LinearLayout(this);
        result.setOrientation(LinearLayout.VERTICAL);
        return result;
    }

    private LinearLayout horizontal() {
        LinearLayout result = new LinearLayout(this);
        result.setOrientation(LinearLayout.HORIZONTAL);
        result.setGravity(Gravity.CENTER_VERTICAL);
        return result;
    }

    private TextView text(String s, int size, int color, boolean bold) {
        TextView label = new TextView(this);
        label.setText(s);
        label.setTextSize(size);
        label.setTextColor(color);
        label.setTypeface(Typeface.DEFAULT, bold ? Typeface.BOLD : Typeface.NORMAL);
        label.setGravity(Gravity.CENTER_VERTICAL);
        return label;
    }

    private void add(LinearLayout parent, View v, int top) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        p.topMargin = dp(top);
        parent.addView(v, p);
    }

    private LinearLayout card(LinearLayout root, String heading) {
        LinearLayout content = vertical();
        content.setPadding(dp(18), dp(18), dp(18), dp(18));
        content.setBackground(rounded(PANEL, 18));
        add(root, content, 14);
        add(content, text(heading, 12, ACCENT, true), 0);
        return content;
    }

    private Button button(String title, boolean primary) {
        Button b = new Button(this);
        b.setAllCaps(false);
        b.setText(title);
        b.setTextSize(14);
        b.setTextColor(primary ? BG : FG);
        b.setTypeface(Typeface.DEFAULT_BOLD);
        b.setBackground(rounded(primary ? ACCENT : Color.rgb(56, 61, 69), 12));
        b.setPadding(dp(8), dp(7), dp(8), dp(7));
        b.setMinHeight(dp(48));
        return b;
    }

    private EditText field(String hint, boolean secret) {
        EditText e = new EditText(this);
        e.setTextColor(FG);
        e.setHintTextColor(MUTED);
        e.setSingleLine(true);
        e.setTextSize(14);
        e.setHint(hint);
        e.setPadding(dp(13), dp(12), dp(13), dp(12));
        e.setBackground(rounded(FIELD, 11));
        if (secret) e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        else e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        return e;
    }

    private void buildScreen() {
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(BG);
        LinearLayout page = vertical();
        page.setPadding(dp(18), dp(18), dp(18), dp(26));
        scroll.addView(page);
        setContentView(scroll);

        LinearLayout header = horizontal();
        TextView logo = text("↓", 30, BG, true);
        logo.setGravity(Gravity.CENTER);
        logo.setBackground(rounded(ACCENT, 14));
        header.addView(logo, new LinearLayout.LayoutParams(dp(50), dp(50)));
        LinearLayout nameBlock = vertical();
        nameBlock.setPadding(dp(12), 0, 0, 0);
        add(nameBlock, text("yandex downloader", 23, FG, true), 0);
        add(nameBlock, text("Музыка и плейлисты", 12, MUTED, false), 3);
        header.addView(nameBlock, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        header.addView(text("v1.0.2", 11, MUTED, false));
        add(page, header, 0);

        LinearLayout auth = card(page, "01  АККАУНТ");
        authText = text("Не выполнен вход", 14, MUTED, false);
        add(auth, authText, 13);
        authButton = button("Войти через Яндекс", true);
        add(auth, authButton, 12);
        authButton.setOnClickListener(v -> loginDevice());
        tokenInput = field("Или OAuth-токен (не сохраняется)", true);
        add(auth, tokenInput, 12);
        tokenButton = button("Подключить токен", false);
        add(auth, tokenButton, 8);
        tokenButton.setOnClickListener(v -> loginWithToken());

        LinearLayout download = card(page, "02  СКАЧИВАНИЕ");
        add(download, text("Ссылка на трек, альбом или плейлист", 13, FG, true), 14);
        urlInput = field("https://music.yandex.ru/...", false);
        add(download, urlInput, 8);
        add(download, text("Папка сохранения", 13, FG, true), 16);
        folderText = text("Не выбрана", 12, MUTED, false);
        add(download, folderText, 7);
        folderButton = button("Выбрать папку", false);
        add(download, folderButton, 8);
        folderButton.setOnClickListener(v -> chooseFolder());
        add(download, text("Качество", 13, FG, true), 16);
        qualitySpinner = new Spinner(this);
        ArrayAdapter<String> options = new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item,
                new String[]{"Высокое · MP3", "Обычное · MP3"});
        qualitySpinner.setAdapter(options);
        qualitySpinner.setBackground(rounded(FIELD, 10));
        add(download, qualitySpinner, 8);
        subfolderCheck = new CheckBox(this);
        subfolderCheck.setText("Папка с названием плейлиста");
        subfolderCheck.setTextColor(FG);
        subfolderCheck.setButtonTintList(android.content.res.ColorStateList.valueOf(ACCENT));
        subfolderCheck.setChecked(true);
        add(download, subfolderCheck, 10);
        LinearLayout actions = horizontal();
        startButton = button("↓  Скачать", true);
        actions.addView(startButton, new LinearLayout.LayoutParams(0, dp(48), 1));
        cancelButton = button("Отмена", false);
        LinearLayout.LayoutParams cancelParams = new LinearLayout.LayoutParams(dp(102), dp(48));
        cancelParams.leftMargin = dp(8);
        actions.addView(cancelButton, cancelParams);
        add(download, actions, 14);
        startButton.setOnClickListener(v -> startDownload());
        cancelButton.setOnClickListener(v -> cancelDownload());

        LinearLayout progress = card(page, "03  ПРОГРЕСС");
        statusText = text("Ожидание ссылки", 15, FG, true);
        add(progress, statusText, 12);
        overallBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        overallBar.setMax(1000);
        overallBar.setProgressTintList(android.content.res.ColorStateList.valueOf(ACCENT));
        add(progress, overallBar, 14);
        detailText = text("0 / 0 треков", 12, MUTED, false);
        add(progress, detailText, 7);
        trackBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        trackBar.setMax(1000);
        trackBar.setProgressTintList(android.content.res.ColorStateList.valueOf(FG));
        add(progress, trackBar, 10);
        speedText = text("Скорость: — · Размер: — · Осталось: —", 12, MUTED, false);
        add(progress, speedText, 7);
        logText = text("Журнал загрузок появится здесь", 12, FG, false);
        logText.setPadding(dp(12), dp(12), dp(12), dp(12));
        logText.setBackground(rounded(FIELD, 12));
        add(progress, logText, 15);
        TextView foot = text("Доступность аудио определяют Яндекс Музыка, подписка и регион. Используйте только записи, которые вправе сохранять.", 11, MUTED, false);
        add(page, foot, 17);
        updateButtons();
    }

    private void log(String message) {
        String old = logText.getText().toString();
        if (old.equals("Журнал загрузок появится здесь")) old = "";
        if (old.length() > 4000) old = old.substring(old.length() - 3000);
        logText.setText(old + message + "\n");
    }

    private void updateButtons() {
        startButton.setEnabled(!busy && !authBusy);
        cancelButton.setEnabled(busy);
        authButton.setEnabled(!busy && !authBusy);
        tokenButton.setEnabled(!busy && !authBusy);
        folderButton.setEnabled(!busy);
    }

    private void chooseFolder() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION |
                Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        startActivityForResult(intent, PICK_FOLDER);
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != PICK_FOLDER || result != RESULT_OK || data == null || data.getData() == null) return;
        Uri uri = data.getData();
        try {
            getContentResolver().takePersistableUriPermission(uri,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
            folderUri = uri;
            getPreferences(MODE_PRIVATE).edit().putString("folder_uri", uri.toString()).apply();
            folderText.setText(uri.getLastPathSegment());
        } catch (Exception ex) {
            Toast.makeText(this, "Не удалось получить доступ к папке: " + ex.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    private void loginDevice() {
        if (busy || authBusy) return;
        authBusy = true;
        authText.setText("Ожидаем код авторизации Яндекса…");
        updateButtons();
        executor.submit(() -> {
            try { Python.getInstance().getModule("android_bridge").callAttr("login_device", listener); }
            catch (Exception ex) { showFailure("auth_error", ex); }
        });
    }

    private void loginWithToken() {
        if (busy || authBusy) return;
        final String token = tokenInput.getText().toString().trim();
        if (token.isEmpty()) { alert("Авторизация", "Введите OAuth-токен или выберите вход через Яндекс."); return; }
        tokenInput.setText("");
        authBusy = true;
        authText.setText("Проверка токена…");
        updateButtons();
        executor.submit(() -> {
            try { Python.getInstance().getModule("android_bridge").callAttr("login_token", token, listener); }
            catch (Exception ex) { showFailure("auth_error", ex); }
        });
    }

    private void startDownload() {
        if (busy || authBusy) return;
        if (!loggedIn) { alert("Авторизация", "Сначала войдите в аккаунт Яндекса."); return; }
        if (folderUri == null) { alert("Папка", "Выберите папку, в которую сохранить музыку."); return; }
        String link = urlInput.getText().toString().trim();
        if (link.isEmpty()) { alert("Ссылка", "Вставьте ссылку из Яндекс Музыки."); return; }
        currentDestination = DocumentFile.fromTreeUri(this, folderUri);
        if (currentDestination == null || !currentDestination.canWrite()) {
            alert("Папка", "Нет прав на запись в выбранную папку. Выберите её заново.");
            return;
        }
        String quality = qualitySpinner.getSelectedItemPosition() == 0 ? "hq" : "nq";
        File cache = new File(getCacheDir(), "job-" + UUID.randomUUID());
        if (!cache.mkdirs()) { alert("Ошибка", "Не удалось создать временную папку."); return; }
        currentCacheDir = cache.getAbsolutePath();
        busy = true;
        statusText.setText("Подключение к Яндекс Музыке…");
        overallBar.setProgress(0);
        trackBar.setProgress(0);
        log("▶ Начало загрузки");
        updateButtons();
        executor.submit(() -> {
            try { Python.getInstance().getModule("android_bridge").callAttr("run_download", link, currentCacheDir, quality, listener); }
            catch (Exception ex) { showFailure("fatal", ex); }
            finally { removeRecursively(cache); }
        });
    }

    private void cancelDownload() {
        if (!busy) return;
        cancelButton.setEnabled(false);
        statusText.setText("Остановка после текущего действия…");
        // Separate thread, since the single executor may be busy downloading.
        new Thread(() -> {
            try { Python.getInstance().getModule("android_bridge").callAttr("cancel"); }
            catch (Exception ex) { showFailure("fatal", ex); }
        }).start();
    }

    private void copyToSelectedDirectory(File source) throws Exception {
        if (!source.isFile() || source.length() == 0) throw new IllegalStateException("Аудиофайл не найден: " + source.getName());
        if (currentDestination == null) throw new IllegalStateException("Папка назначения потеряна");
        if (currentDestination.findFile(source.getName()) != null) { source.delete(); return; }
        String mime = source.getName().endsWith(".m4a") ? "audio/mp4"
                : source.getName().endsWith(".flac") ? "audio/flac"
                : source.getName().endsWith(".aac") ? "audio/aac" : "audio/mpeg";
        DocumentFile target = currentDestination.createFile(mime, source.getName());
        if (target == null) throw new IllegalStateException("Android отказал в создании файла");
        try (InputStream in = new FileInputStream(source);
             OutputStream out = getContentResolver().openOutputStream(target.getUri(), "w")) {
            if (out == null) throw new IllegalStateException("Android не открыл файл для записи");
            byte[] buffer = new byte[65536];
            long written = 0;
            int read;
            while ((read = in.read(buffer)) != -1) {
                out.write(buffer, 0, read);
                written += read;
            }
            out.flush();
            if (written != source.length()) throw new IllegalStateException("Файл скопирован не полностью");
        } catch (Exception ex) {
            target.delete();
            throw ex;
        }
        source.delete();
    }

    private String sanitized(String raw) {
        String value = raw.replaceAll("[\\\\/:*?\"<>|\\p{Cntrl}]", "_").trim();
        return value.length() > 130 ? value.substring(0, 130) : value;
    }

    private static String bytes(long value) {
        if (value < 0) return "—";
        double n = value;
        String[] units = {"Б", "КБ", "МБ", "ГБ"};
        int i = 0;
        while (n >= 1024 && i < units.length-1) { n /= 1024; i++; }
        return String.format(java.util.Locale.US, "%.1f %s", n, units[i]);
    }

    private void displayEvent(String kind, JSONObject d) {
        switch (kind) {
            case "auth_code":
                String address = d.optString("url", "https://ya.ru/device");
                String code = d.optString("code", "");
                authText.setText("Введите код на странице Яндекса: " + code);
                new AlertDialog.Builder(this)
                    .setTitle("Авторизация через Яндекс")
                    .setMessage("Код: " + code + "\n\nОткройте страницу Яндекса, введите код и подтвердите вход. Вернитесь в приложение.")
                    .setPositiveButton("Открыть Яндекс", (dialog, which) -> {
                        try { startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(address))); }
                        catch (Exception e) { log("Не удалось открыть браузер: " + e.getMessage()); }
                    })
                    .setNegativeButton("Закрыть", null).show();
                break;
            case "auth_ok":
                authBusy = false; loggedIn = true;
                authText.setText("● Аккаунт подключён");
                log("✓ Успешный вход"); updateButtons();
                break;
            case "auth_error":
                authBusy = false; loggedIn = false;
                authText.setText("Не удалось войти");
                log("✕ " + d.optString("message")); updateButtons();
                break;
            case "resolved":
                log("Найдено треков: " + d.optInt("count") + " · " + d.optString("title"));
                detailText.setText("0 / " + d.optInt("count") + " треков");
                break;
            case "track":
                statusText.setText(d.optString("name"));
                detailText.setText("Трек " + d.optInt("index") + " из " + d.optInt("count"));
                trackBar.setProgress(0);
                speedText.setText("Скорость: — · Размер: — · Осталось: —");
                break;
            case "bytes":
                long got = d.optLong("got", 0);
                long total = d.isNull("total") ? -1 : d.optLong("total", -1);
                double speed = d.isNull("speed") ? 0 : d.optDouble("speed", 0);
                if (total > 0) trackBar.setProgress((int)(Math.min(1, (double) got / total) * 1000));
                String eta = total > 0 && speed > 0 ? Math.max(0, (int)((total-got)/speed)) + " c" : "—";
                speedText.setText("Скорость: " + (speed > 0 ? bytes((long)speed)+"/с" : "—") + "\nЗагружено: " + bytes(got) + " / " + bytes(total) + " · Осталось: " + eta);
                break;
            case "saved":
                trackBar.setProgress(1000);
                log("✓ " + d.optString("name"));
                break;
            case "skipped":
                trackBar.setProgress(1000);
                log("↷ " + d.optString("name"));
                break;
            case "error":
                log("✕ " + d.optString("name") + ": " + d.optString("message"));
                break;
            case "overall":
                int count = d.optInt("count", 0);
                int index = d.optInt("index", 0);
                if (count > 0) overallBar.setProgress((int)(1000.0 * index / count));
                detailText.setText("Обработано " + index + " / " + count);
                break;
            case "finished":
                busy = false;
                statusText.setText("Готово: " + d.optInt("done") + " загружено, " + d.optInt("failed") + " ошибок");
                log("■ Завершено"); updateButtons();
                break;
            case "cancelled":
                busy = false; statusText.setText("Загрузка отменена");
                log("■ Отменено"); updateButtons();
                break;
            case "fatal":
                busy = false; statusText.setText("Ошибка загрузки");
                log("✕ " + d.optString("message")); updateButtons();
                break;
            default: break;
        }
    }

    private void showFailure(String kind, Exception ex) {
        runOnUiThread(() -> {
            try { displayEvent(kind, new JSONObject().put("message", ex.getMessage())); }
            catch (Exception ignore) { statusText.setText("Ошибка: " + ex.getMessage()); }
        });
    }

    private void alert(String title, String message) {
        new AlertDialog.Builder(this).setTitle(title).setMessage(message).setPositiveButton("ОК", null).show();
    }

    private static void removeRecursively(File file) {
        if (file.isDirectory()) {
            File[] items = file.listFiles();
            if (items != null) for (File child : items) removeRecursively(child);
        }
        file.delete();
    }

    @Override protected void onDestroy() {
        super.onDestroy();
        if (busy) cancelDownload();
        executor.shutdown();
    }
}