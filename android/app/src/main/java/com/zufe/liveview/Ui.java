package com.zufe.liveview;

import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Typeface;
import android.util.TypedValue;
import android.widget.Button;
import android.widget.TextView;

/** 颜色和常用控件的统一出口，界面全部用代码拼，不依赖布局文件。 */
public final class Ui {

    // 浅色主题（和电脑端一致）
    public static final int BG = 0xFFF4F6FA;
    public static final int SURFACE = 0xFFFFFFFF;
    public static final int SURFACE_HI = 0xFFEEF2F8;
    public static final int LINE = 0xFFE3E9F2;
    public static final int TEXT = 0xFF0F172A;
    public static final int DIM = 0xFF55657A;
    public static final int FAINT = 0xFF94A3B8;
    public static final int ACCENT = 0xFF2563EB;
    public static final int ACCENT_HI = 0xFF3B82F6;
    public static final int OK = 0xFF0E9F6E;
    public static final int WARN = 0xFFD97706;
    public static final int ERR = 0xFFDC2626;
    public static final int SOFT_OK = 0xFFE7F7F0;

    // 播放页浮层（视频上永远用深色，保证可读）
    public static final int CHIP_IDLE = 0xCC1B2431;
    public static final int OVERLAY_BG = 0xE6101720;

    private Ui() {
    }

    public static int dp(Context c, float v) {
        return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v,
                c.getResources().getDisplayMetrics()));
    }

    public static TextView text(Context c, String s, float sp, int color, boolean bold) {
        TextView t = new TextView(c);
        t.setText(s);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        t.setTextColor(color);
        t.setTypeface(null, bold ? Typeface.BOLD : Typeface.NORMAL);
        return t;
    }

    /** 等宽字体（房间号、时间戳用）。 */
    public static TextView mono(Context c, String s, float sp, int color, boolean bold) {
        TextView t = text(c, s, sp, color, bold);
        t.setTypeface(Typeface.MONOSPACE, bold ? Typeface.BOLD : Typeface.NORMAL);
        return t;
    }

    public static Button button(Context c, String s, int bg, int fg) {
        Button b = new Button(c);
        b.setAllCaps(false);
        b.setText(s);
        b.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        b.setTextColor(fg);
        b.setBackgroundTintList(ColorStateList.valueOf(bg));
        b.setMinHeight(0);
        b.setMinimumHeight(0);
        b.setMinWidth(0);
        b.setMinimumWidth(0);
        b.setPadding(dp(c, 14), dp(c, 8), dp(c, 14), dp(c, 8));
        return b;
    }

    /** 播放页那种半透明底的小按钮。 */
    public static Button chip(Context c, String s, boolean active) {
        Button b = button(c, s, active ? ACCENT : CHIP_IDLE, active ? 0xFFFFFFFF : 0xFFE9EFF7);
        b.setTextSize(TypedValue.COMPLEX_UNIT_SP, 13);
        b.setPadding(dp(c, 12), dp(c, 6), dp(c, 12), dp(c, 6));
        return b;
    }

    /** 切换 chip 的选中态（播放页切画面时用）。 */
    public static void setChip(Button b, boolean active) {
        b.setBackgroundTintList(ColorStateList.valueOf(active ? ACCENT : CHIP_IDLE));
        b.setTextColor(active ? 0xFFFFFFFF : 0xFFE9EFF7);
    }
}
