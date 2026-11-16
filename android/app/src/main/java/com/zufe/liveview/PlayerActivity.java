package com.zufe.liveview;

import android.app.Activity;
import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.view.TextureView;
import android.os.Build;
import android.app.AlertDialog;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.TextUtils;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import androidx.media3.common.MediaItem;
import androidx.media3.common.PlaybackException;
import androidx.media3.common.Player;
import androidx.media3.datasource.DefaultHttpDataSource;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.exoplayer.source.ProgressiveMediaSource;
import androidx.media3.common.VideoSize;

import java.util.List;

/** 播放页：课堂画面 / 电脑桌面两路 FLV + 底部实时字幕 + 右侧全文转写。 */
public class PlayerActivity extends Activity {

    private final Handler ui = new Handler(Looper.getMainLooper());
    private final Runnable hideBar = new Runnable() {
        @Override
        public void run() {
            setBarVisible(false);
        }
    };

    private ExoPlayer player;
    private TextureView tex;
    private LinearLayout bar;
    private TextView hint;
    private TextView info;
    private Button btnMain;
    private Button btnPpt;
    private Button btnExtra;
    private Button btnSub;
    private Button btnPanel;
    private Button btnFull;
    private TextView subBar;
    private FrameLayout panel;
    private LinearLayout list;
    private ScrollView listScroll;
    private TextView panelCount;

    private String room = "";
    private String course = "";
    private String mainUrl = "";
    private String pptUrl = "";
    private String extraUrl = "";
    private String link = "";
    private String enc = "";
    private String fid = "";
    private String speechid = "";

    private boolean showingPpt;
    private boolean showingExtra;
    private boolean fullscreen;
    private boolean subOn = true;
    private boolean panelOn;
    private int retries;
    private boolean failShown;
    private boolean stoppedOnce;
    private int shownSegs;
    private int videoW;
    private int videoH;

    private Transcripts subs;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        Intent it = getIntent();
        room = nz(it.getStringExtra("room")).trim();
        course = nz(it.getStringExtra("course")).trim();
        mainUrl = nz(it.getStringExtra("main"));
        pptUrl = nz(it.getStringExtra("ppt"));
        extraUrl = nz(it.getStringExtra("other"));
        link = nz(it.getStringExtra("link"));
        enc = nz(it.getStringExtra("enc"));
        fid = nz(it.getStringExtra("fid"));
        speechid = nz(it.getStringExtra("speechid"));
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        buildUi();
        play(false);
        startSubs();
    }

    private static String nz(String s) {
        return s == null ? "" : s;
    }

    private int dp(float v) {
        return Ui.dp(this, v);
    }

    private int screenWidth() {
        return getResources().getDisplayMetrics().widthPixels;
    }

    private void buildUi() {
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.BLACK);
        root.setFitsSystemWindows(true);

        tex = new TextureView(this);
        FrameLayout.LayoutParams texLp = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT);
        texLp.gravity = Gravity.CENTER;
        root.addView(tex, texLp);

        View catcher = new View(this);
        catcher.setBackgroundColor(Color.TRANSPARENT);
        catcher.setOnClickListener(v -> {
            if (bar.getVisibility() == View.VISIBLE) {
                setBarVisible(false);
            } else {
                setBarVisible(true);
            }
        });
        root.addView(catcher, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        // 顶部按钮：横向可滚动，窄屏也不会挤成一团
        bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.setPadding(dp(6), dp(6), dp(6), dp(6));
        bar.setBackgroundColor(0xD9101418);

        btnMain = Ui.chip(this, "课堂画面", true);
        btnMain.setOnClickListener(v -> switchTo(false));
        bar.addView(btnMain, margin(dp(4), dp(2)));

        btnPpt = Ui.chip(this, "电脑桌面", false);
        btnPpt.setOnClickListener(v -> switchTo(true));
        bar.addView(btnPpt, margin(dp(4), dp(2)));
        btnPpt.setEnabled(!pptUrl.isEmpty());
        btnPpt.setAlpha(pptUrl.isEmpty() ? 0.4f : 1f);

        btnExtra = Ui.chip(this, "教室全景", false);
        btnExtra.setOnClickListener(v -> switchToExtra());
        btnExtra.setVisibility(extraUrl.isEmpty() ? View.GONE : View.VISIBLE);
        bar.addView(btnExtra, margin(dp(4), dp(2)));

        btnSub = Ui.chip(this, "字幕", true);
        btnSub.setOnClickListener(v -> {
            subOn = !subOn;
            refreshLabels();
            applySubBar();
        });
        bar.addView(btnSub, margin(dp(4), dp(2)));

        btnPanel = Ui.chip(this, "全文", false);
        btnPanel.setOnClickListener(v -> {
            panelOn = !panelOn;
            panel.setVisibility(panelOn ? View.VISIBLE : View.GONE);
            refreshLabels();
        });
        bar.addView(btnPanel, margin(dp(4), dp(2)));

        btnFull = Ui.chip(this, "全屏", false);
        btnFull.setOnClickListener(v -> toggleFullscreen());
        bar.addView(btnFull, margin(dp(4), dp(2)));

        Button btnRetry = Ui.chip(this, "重连", false);
        btnRetry.setOnClickListener(v -> {
            retries = 0;
            play(true);
            startSubs();
        });
        bar.addView(btnRetry, margin(dp(4), dp(2)));

        Button btnClose = Ui.chip(this, "退出", false);
        btnClose.setOnClickListener(v -> finish());
        bar.addView(btnClose, margin(dp(4), dp(2)));

        HorizontalScrollView scroller = new HorizontalScrollView(this);
        scroller.setHorizontalScrollBarEnabled(false);
        scroller.addView(bar);
        FrameLayout.LayoutParams slp = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        slp.gravity = Gravity.TOP;
        slp.topMargin = dp(8);
        root.addView(scroller, slp);
        this.scroller = scroller;

        // 底部字幕条
        subBar = new TextView(this);
        subBar.setTextColor(0xFFFFFFFF);
        subBar.setTextSize(TypedValue.COMPLEX_UNIT_SP, 19f);
        subBar.setGravity(Gravity.CENTER);
        subBar.setPadding(dp(18), dp(11), dp(18), dp(11));
        subBar.setShadowLayer(dp(3), 0f, dp(1), 0xCC000000);
        subBar.setLineSpacing(dp(3), 1f);
        subBar.setMaxLines(3);
        subBar.setEllipsize(TextUtils.TruncateAt.END);
        GradientDrawable subBg = new GradientDrawable();
        subBg.setColor(0xCC000000);
        subBg.setCornerRadius(dp(12));
        subBar.setBackground(subBg);
        subBar.setVisibility(View.GONE);
        FrameLayout.LayoutParams sbp = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        sbp.gravity = Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL;
        sbp.bottomMargin = dp(46);
        root.addView(subBar, sbp);

        // 右侧全文面板
        panel = new FrameLayout(this);
        panel.setVisibility(View.GONE);
        GradientDrawable panelBg = new GradientDrawable();
        panelBg.setColor(0xFFFFFFFF);
        panelBg.setCornerRadius(dp(14));
        panel.setBackground(panelBg);
        panel.setElevation(dp(8));
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(dp(14), dp(12), dp(10), dp(10));

        LinearLayout head = new LinearLayout(this);
        head.setOrientation(LinearLayout.HORIZONTAL);
        head.setGravity(Gravity.CENTER_VERTICAL);
        TextView title = Ui.text(this, "全部说过的话", 14, Ui.TEXT, true);
        head.addView(title, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        panelCount = Ui.mono(this, "", 11, Ui.DIM, false);
        head.addView(panelCount);
        Button close = Ui.chip(this, "收起", false);
        close.setOnClickListener(v -> {
            panelOn = false;
            panel.setVisibility(View.GONE);
            refreshLabels();
        });
        LinearLayout.LayoutParams closeLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        closeLp.leftMargin = dp(8);
        head.addView(close, closeLp);
        col.addView(head);

        View hr = new View(this);
        hr.setBackgroundColor(Ui.LINE);
        LinearLayout.LayoutParams hrLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, Math.max(1, dp(1)));
        hrLp.topMargin = dp(8);
        col.addView(hr, hrLp);

        listScroll = new ScrollView(this);
        listScroll.setVerticalScrollBarEnabled(true);
        list = new LinearLayout(this);
        list.setOrientation(LinearLayout.VERTICAL);
        listScroll.addView(list);
        LinearLayout.LayoutParams listLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f);
        listLp.topMargin = dp(6);
        col.addView(listScroll, listLp);

        panel.addView(col, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        int pw = (int) Math.min(dp(340), screenWidth() * 0.84f);
        FrameLayout.LayoutParams plp = new FrameLayout.LayoutParams(
                pw, ViewGroup.LayoutParams.MATCH_PARENT);
        plp.gravity = Gravity.END;
        plp.topMargin = dp(56);
        plp.bottomMargin = dp(12);
        plp.rightMargin = dp(8);
        root.addView(panel, plp);

        info = Ui.text(this, "", 12, 0xFFD7E2EE, false);
        info.setBackgroundColor(0x88101418);
        info.setPadding(dp(10), dp(4), dp(10), dp(4));
        FrameLayout.LayoutParams ilp = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        ilp.gravity = Gravity.BOTTOM | Gravity.START;
        ilp.leftMargin = dp(10);
        ilp.bottomMargin = dp(10);
        root.addView(info, ilp);

        hint = Ui.text(this, "点一下屏幕出按钮", 12, 0xFFD7E2EE, false);
        hint.setPadding(dp(10), dp(4), dp(10), dp(4));
        FrameLayout.LayoutParams hlp = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        hlp.gravity = Gravity.CENTER;
        root.addView(hint, hlp);
        ui.postDelayed(() -> hint.setVisibility(View.GONE), 3000);

        setContentView(root);
        refreshLabels();
    }

    private HorizontalScrollView scroller;

    private LinearLayout.LayoutParams margin(int h, int v) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        p.leftMargin = h;
        p.rightMargin = h;
        p.topMargin = v;
        p.bottomMargin = v;
        return p;
    }

    private void refreshLabels() {
        String type = showingExtra ? "教室全景" : (showingPpt ? "电脑桌面" : "课堂画面");
        StringBuilder sb = new StringBuilder(type);
        if (!room.isEmpty()) {
            sb.append(" · ").append(room);
        }
        if (!course.isEmpty()) {
            sb.append(" · ").append(course);
        }
        info.setText(sb.toString());
        Ui.setChip(btnMain, !showingPpt && !showingExtra);
        Ui.setChip(btnPpt, showingPpt && !showingExtra);
        if (btnExtra != null) {
            Ui.setChip(btnExtra, showingExtra);
            btnExtra.setVisibility(extraUrl.isEmpty() ? View.GONE : View.VISIBLE);
            btnExtra.setAlpha(extraUrl.isEmpty() ? 0.4f : 1f);
        }
        Ui.setChip(btnSub, subOn);
        Ui.setChip(btnPanel, panelOn);
        btnPpt.setEnabled(!pptUrl.isEmpty());
        btnPpt.setAlpha(pptUrl.isEmpty() ? 0.4f : 1f);
        btnFull.setText(fullscreen ? "退出全屏" : "全屏");
    }

    private void switchTo(boolean ppt) {
        if (ppt && pptUrl.isEmpty()) {
            toast("这间教室没有电脑桌面画面");
            return;
        }
        if (ppt == showingPpt && !showingExtra) {
            return;
        }
        showingExtra = false;
        showingPpt = ppt;
        retries = 0;
        play(true);
    }

    private void switchToExtra() {
        if (extraUrl.isEmpty()) {
            toast("这间教室没有教室全景画面");
            return;
        }
        if (showingExtra) {
            return;
        }
        showingExtra = true;
        showingPpt = false;
        retries = 0;
        play(true);
    }

    private String currentUrl() {
        if (showingExtra && !extraUrl.isEmpty()) {
            return extraUrl;
        }
        if (showingPpt) {
            return pptUrl;
        }
        if (!mainUrl.isEmpty()) {
            return mainUrl;
        }
        return pptUrl;
    }

    private void play(boolean keepFullscreen) {
        String url = currentUrl();
        if (url.isEmpty()) {
            toast("没有可播放的地址");
            return;
        }
        hint.setVisibility(View.GONE);
        if (player == null) {
            player = new ExoPlayer.Builder(this).build();
            player.setVideoTextureView(tex);
            player.addListener(new Player.Listener() {
                @Override
                public void onPlayerError(PlaybackException error) {
                    onError(error);
                }

                @Override
                public void onVideoSizeChanged(VideoSize size) {
                    videoW = size.width;
                    videoH = Math.max(1, size.height);
                    ui.post(() -> {
                        fitVideo();
                        placeSubBar();
                    });
                }
            });
        }
        DefaultHttpDataSource.Factory http = new DefaultHttpDataSource.Factory()
                .setUserAgent(HttpHelper.UA)
                .setConnectTimeoutMs(15000)
                .setReadTimeoutMs(20000)
                .setAllowCrossProtocolRedirects(true);
        ProgressiveMediaSource.Factory factory = new ProgressiveMediaSource.Factory(http);
        player.setMediaSource(factory.createMediaSource(MediaItem.fromUri(url)));
        player.setPlayWhenReady(true);
        player.prepare();
        refreshLabels();
    }

    private void onError(PlaybackException e) {
        String msg = e.getErrorCodeName();
        if (e.getMessage() != null && !e.getMessage().isEmpty()) {
            msg = msg + "：" + e.getMessage();
        }
        final String text = msg;
        runOnUiThread(() -> {
            hint.setText("播放失败（" + text + "），正在重试…");
            hint.setVisibility(View.VISIBLE);
            if (retries < 3) {
                retries++;
                ui.postDelayed(() -> play(showingPpt), 1500L * retries);
            } else {
                hint.setText("播放失败：" + text + "\n点「重连」再来一次");
                showFailDialog(text);
            }
        });
    }

    private void showFailDialog(String text) {
        if (isFinishing() || failShown) return;
        failShown = true;
        new AlertDialog.Builder(this)
                .setTitle("打不开这路画面")
                .setMessage("原因：" + text + "\n\n多半是这间教室现在没在直播（上课时间才有），\n或者登录状态失效了。")
                .setPositiveButton("重试", (d, w) -> {
                    failShown = false;
                    retries = 0;
                    play(true);
                })
                .setNegativeButton("返回列表", (d, w) -> finish())
                .show();
    }

    // ---------- 实时字幕 ----------

    private void startSubs() {
        if (subs != null) {
            subs.stop();
            subs = null;
        }
        subs = new Transcripts(mainUrl, enc, fid, speechid, link);
        subs.setListener(t -> applySubs(t));
        subs.start();
    }

    private void applySubs(Transcripts t) {
        String mid = t.mid();
        List<Transcripts.Seg> segs = t.segments();
        if (mid.isEmpty() && !segs.isEmpty()) {
            mid = segs.get(segs.size() - 1).text;
        }
        subBar.setText(mid);
        applySubBar();

        if (segs.size() != shownSegs) {
            shownSegs = segs.size();
            panelCount.setText(segs.size() + " 段");
            for (int i = list.getChildCount(); i < segs.size(); i++) {
                Transcripts.Seg s = segs.get(i);
                LinearLayout row = new LinearLayout(this);
                row.setOrientation(LinearLayout.HORIZONTAL);
                row.setPadding(0, dp(4), 0, dp(4));
                TextView time = Ui.mono(this, s.clock, 11, Ui.FAINT, false);
                LinearLayout.LayoutParams tlp = new LinearLayout.LayoutParams(
                        ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
                tlp.rightMargin = dp(8);
                row.addView(time, tlp);
                TextView body = Ui.text(this, s.text, 13, Ui.TEXT, false);
                body.setLineSpacing(dp(2), 1f);
                row.addView(body, new LinearLayout.LayoutParams(
                        0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
                list.addView(row);
            }
            if (listScroll != null) {
                listScroll.post(() -> listScroll.fullScroll(View.FOCUS_DOWN));
            }
        }
    }

    private void applySubBar() {
        boolean show = subOn && subBar != null && subBar.getText().length() > 0;
        subBar.setVisibility(show ? View.VISIBLE : View.GONE);
        if (show) {
            placeSubBar();
        }
    }

    /** 按比例把画面贴在窗口中间（相当于 FIT 模式），黑边留在上下。 */
    private void fitVideo() {
        if (tex == null) {
            return;
        }
        View parent = (View) tex.getParent();
        int vw = parent.getWidth();
        int vh = parent.getHeight();
        if (vw <= 0 || vh <= 0 || videoW <= 0 || videoH <= 0) {
            return;
        }
        float scale = Math.min(vw / (float) videoW, vh / (float) videoH);
        int cw = Math.max(1, (int) (videoW * scale));
        int ch = Math.max(1, (int) (videoH * scale));
        FrameLayout.LayoutParams lp = (FrameLayout.LayoutParams) tex.getLayoutParams();
        lp.width = cw;
        lp.height = ch;
        lp.gravity = Gravity.CENTER;
        tex.setLayoutParams(lp);
    }

    /** 把字幕条贴在画面（不是窗口）的底部：竖屏有黑边时跟着黑边往上。 */
    private void placeSubBar() {
        if (subBar == null || tex == null) {
            return;
        }
        View parent = (View) tex.getParent();
        int vw = parent.getWidth();
        int vh = parent.getHeight();
        if (vw <= 0 || vh <= 0) {
            return;
        }
        int contentH = tex.getHeight() > 0 ? tex.getHeight() : vh;
        int contentW = tex.getWidth() > 0 ? tex.getWidth() : vw;
        int bottomGap = (vh - contentH) / 2;
        FrameLayout.LayoutParams lp = (FrameLayout.LayoutParams) subBar.getLayoutParams();
        lp.gravity = Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL;
        lp.bottomMargin = bottomGap + dp(16);
        lp.width = ViewGroup.LayoutParams.WRAP_CONTENT;
        subBar.setLayoutParams(lp);
        subBar.setMaxWidth((int) (contentW * 0.88f));
    }

    private void setBarVisible(boolean visible) {
        bar.setVisibility(visible ? View.VISIBLE : View.GONE);
        ui.removeCallbacks(hideBar);
        if (visible) {
            ui.postDelayed(hideBar, 5000);
        }
    }

    private void toggleFullscreen() {
        fullscreen = !fullscreen;
        if (fullscreen) {
            setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE);
        } else {
            setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED);
        }
        applyImmersive();
        refreshLabels();
        setBarVisible(true);
    }

    private void applyImmersive() {
        View decor = getWindow().getDecorView();
        if (Build.VERSION.SDK_INT >= 30) {
            WindowInsetsController c = getWindow().getInsetsController();
            if (fullscreen) {
                decor.setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN);
                if (c != null) {
                    c.hide(WindowInsets.Type.statusBars() | WindowInsets.Type.navigationBars());
                    c.setSystemBarsBehavior(
                            WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
                }
            } else {
                if (c != null) {
                    c.show(WindowInsets.Type.statusBars() | WindowInsets.Type.navigationBars());
                }
                decor.setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
            }
            return;
        }
        if (fullscreen) {
            decor.setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                    | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY);
        } else {
            decor.setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
        }
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            applyImmersive();
        }
    }

    private void toast(String msg) {
        android.widget.Toast.makeText(this, msg, android.widget.Toast.LENGTH_SHORT).show();
    }

    @Override
    protected void onStop() {
        super.onStop();
        if (player != null) {
            player.pause();
            stoppedOnce = true;
        }
        if (subs != null) {
            subs.stop();
        }
    }

    @Override
    protected void onStart() {
        super.onStart();
        if (stoppedOnce && player != null) {
            stoppedOnce = false;
            ui.postDelayed(() -> play(showingPpt), 300);
        }
        if (subs != null && subs.count() == 0) {
            startSubs();
        }
    }

    @Override
    protected void onDestroy() {
        ui.removeCallbacks(hideBar);
        if (subs != null) {
            subs.stop();
            subs = null;
        }
        if (player != null) {
            player.release();
            player = null;
        }
        if (tex != null) {
            tex.setVisibility(View.GONE);
        }
        super.onDestroy();
    }
}
