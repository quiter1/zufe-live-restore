package com.zufe.liveview;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.webkit.WebStorage;
import android.widget.AbsListView;
import android.widget.AdapterView;
import android.widget.BaseAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.List;

/** 首页：教室列表，点一间就去取画面。 */
public class MainActivity extends Activity {

    private static final int REQ_LOGIN = 7;

    private final Handler ui = new Handler(Looper.getMainLooper());
    private final List<String> names = new ArrayList<>();

    private ListView list;
    private RoomAdapter adapter;
    private TextView status;
    private TextView subtitle;
    private ProgressBar spin;
    private Button addBtn;
    private Button settingsBtn;

    private boolean busy;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        Store.init(this);
        getWindow().setStatusBarColor(Ui.BG);
        getWindow().setNavigationBarColor(Ui.BG);
        buildUi();
        reload();
    }

    @Override
    protected void onResume() {
        super.onResume();
        reload();
    }

    private int dp(float v) {
        return Ui.dp(this, v);
    }

    private void buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Ui.BG);
        root.setFitsSystemWindows(true);

        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(dp(18), dp(16), dp(14), dp(10));

        LinearLayout titles = new LinearLayout(this);
        titles.setOrientation(LinearLayout.VERTICAL);
        LinearLayout.LayoutParams tp = new LinearLayout.LayoutParams(0,
                ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        header.addView(titles, tp);

        TextView title = Ui.text(this, "智播课堂 Live", 22, Ui.TEXT, true);
        titles.addView(title);
        subtitle = Ui.text(this, "", 12, Ui.DIM, false);
        subtitle.setPadding(0, dp(3), 0, 0);
        titles.addView(subtitle);

        spin = new ProgressBar(this);
        spin.setIndeterminate(true);
        LinearLayout.LayoutParams sp = new LinearLayout.LayoutParams(dp(22), dp(22));
        sp.rightMargin = dp(10);
        spin.setVisibility(View.GONE);
        header.addView(spin, sp);

        settingsBtn = Ui.button(this, "设置", Ui.SURFACE_HI, Ui.TEXT);
        settingsBtn.setOnClickListener(v -> settingsDialog());
        header.addView(settingsBtn);
        root.addView(header, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        status = Ui.text(this, "", 12, Ui.DIM, false);
        status.setPadding(dp(18), 0, dp(18), dp(8));
        root.addView(status);

        list = new ListView(this);
        list.setDivider(null);
        list.setDividerHeight(dp(8));
        list.setPadding(dp(14), dp(4), dp(14), dp(4));
        list.setClipToPadding(false);
        list.setVerticalScrollBarEnabled(false);
        list.setSelector(android.R.color.transparent);
        adapter = new RoomAdapter();
        list.setAdapter(adapter);
        list.setOnItemClickListener(new AdapterView.OnItemClickListener() {
            @Override
            public void onItemClick(AdapterView<?> parent, View view, int position, long id) {
                play(names.get(position));
            }
        });
        list.setOnItemLongClickListener(new AdapterView.OnItemLongClickListener() {
            @Override
            public boolean onItemLongClick(AdapterView<?> parent, View view, int position, long id) {
                confirmRemove(names.get(position));
                return true;
            }
        });
        root.addView(list, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));

        LinearLayout bottom = new LinearLayout(this);
        bottom.setOrientation(LinearLayout.HORIZONTAL);
        bottom.setPadding(dp(14), dp(8), dp(14), dp(14));

        addBtn = Ui.button(this, "＋ 添加教室", Ui.SURFACE_HI, Ui.TEXT);
        addBtn.setOnClickListener(v -> addRoomDialog());
        LinearLayout.LayoutParams bp = new LinearLayout.LayoutParams(0,
                ViewGroup.LayoutParams.WRAP_CONTENT, 1f);
        bp.rightMargin = dp(10);
        bottom.addView(addBtn, bp);

        Button clearBtn = Ui.button(this, "清除登录", Ui.SURFACE_HI, Ui.DIM);
        clearBtn.setOnClickListener(v -> clearLogin());
        bottom.addView(clearBtn);
        root.addView(bottom, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        setContentView(root);
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
    }

    private void reload() {
        names.clear();
        names.addAll(Store.roomNames(this));
        if (adapter != null) {
            adapter.notifyDataSetChanged();
        }
        String last = Store.lastRoom(this);
        if (names.isEmpty()) {
            subtitle.setText("还没有教室，先添加一间");
        } else {
            subtitle.setText("共 " + names.size() + " 间 · " + (last.isEmpty() ? "点教室开始看" : "上次看 " + last));
        }
        if (!busy) {
            status.setText("点教室名字开始看，长按可以删掉");
            status.setTextColor(Ui.DIM);
        }
    }

    private void setBusy(boolean on, String text) {
        busy = on;
        spin.setVisibility(on ? View.VISIBLE : View.GONE);
        addBtn.setEnabled(!on);
        settingsBtn.setEnabled(!on);
        if (text != null) {
            status.setText(text);
            status.setTextColor(Ui.DIM);
        }
    }

    private void play(final String room) {
        if (busy) {
            toast("正在取画面，稍等一下");
            return;
        }
        final String link = Store.firstLink(this, room);
        if (link == null) {
            toast("这间教室还没有直播链接");
            return;
        }
        Store.setLastRoom(this, room);
        setBusy(true, "正在取「" + room + "」的画面地址…");
        new Thread("resolve-" + room) {
            @Override
            public void run() {
                try {
                    final Streams s = Resolver.resolve(MainActivity.this, room, link);
                    Store.saveStream(MainActivity.this, room, s);
                    final boolean ok = probe(s.main);
                    ui.post(() -> {
                        setBusy(false, null);
                        if (ok) {
                            openPlayer(room, s);
                        } else {
                            noPicture(room, s);
                        }
                    });
                } catch (Resolver.NeedLogin e) {
                    final String msg = e.getMessage() == null ? "需要登录" : e.getMessage();
                    ui.post(() -> {
                        setBusy(false, null);
                        askLogin(room, link, msg);
                    });
                } catch (final Exception e) {
                    final String msg = e.getMessage() == null ? e.toString() : e.getMessage();
                    ui.post(() -> {
                        setBusy(false, null);
                        failed(room, msg);
                    });
                }
            }
        }.start();
    }

    private void openPlayer(String room, Streams s) {
        Intent i = new Intent(this, PlayerActivity.class);
        i.putExtra("room", room);
        i.putExtra("course", s.course);
        i.putExtra("main", s.main);
        i.putExtra("ppt", s.ppt);
        i.putExtra("other", s.other);
        i.putExtra("enc", s.enc);
        i.putExtra("fid", s.fid);
        i.putExtra("speechid", s.speechid);
        i.putExtra("link", Store.firstLink(this, room));
        startActivity(i);
    }

    private static boolean probe(String url) {
        if (url == null || url.isEmpty()) return false;
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(url).openConnection();
            c.setRequestProperty("User-Agent", HttpHelper.UA);
            c.setRequestProperty("Range", "bytes=0-1023");
            c.setConnectTimeout(8000);
            c.setReadTimeout(8000);
            c.setInstanceFollowRedirects(true);
            int code = c.getResponseCode();
            if (code != 200 && code != 206) return false;
            InputStream in = c.getInputStream();
            try {
                return in.read() >= 0;
            } finally {
                in.close();
            }
        } catch (Exception e) {
            return false;
        } finally {
            if (c != null) c.disconnect();
        }
    }

    private void noPicture(final String room, final Streams s) {
        status.setText("这间教室现在没有画面");
        status.setTextColor(Ui.WARN);
        new AlertDialog.Builder(this)
                .setTitle("这间教室现在没有画面")
                .setMessage("地址是拿到了，但没有可播的画面：多半是这堂课没在上课、没开直播，或者直播刚结束；也可能是登录状态失效了。\n\n上课时间再试一次；如果确定在上课，点教室后在弹窗里选「去登录」重新登一次。")
                .setPositiveButton("知道了", null)
                .setNeutralButton("仍然打开", (d, w) -> openPlayer(room, s))
                .show();
    }

    private void failed(String room, String msg) {
        status.setText("没取到画面：" + msg);
        status.setTextColor(Ui.WARN);
        boolean auth = msg != null && (msg.contains("密码") || msg.contains("账号") || msg.contains("登录"));
        Streams cache = auth ? null : Store.cachedStream(this, room);
        if (cache != null) {
            new AlertDialog.Builder(this)
                    .setTitle("没取到画面")
                    .setMessage(msg + "\n\n这间教室上次取到过画面地址，要不要拿上次的再试一下？")
                    .setPositiveButton("用上次的", (d, w) -> {
                        new Thread(() -> {
                            final boolean ok = probe(cache.main);
                            ui.post(() -> {
                                if (ok) {
                                    openPlayer(room, cache);
                                } else {
                                    toast("上次的地址已经过期了（直播地址有时效），等上课再取一次");
                                }
                            });
                        }, "probe-cache").start();
                    })
                    .setNegativeButton("算了", null)
                    .show();
        } else {
            new AlertDialog.Builder(this)
                    .setTitle("没取到画面")
                    .setMessage(msg)
                    .setPositiveButton("知道了", null)
                    .setNeutralButton("去登录", (d, w) -> askLogin(room, Store.firstLink(this, room), msg))
                    .show();
        }
    }

    private void askLogin(final String room, final String link, String why) {
        status.setText("需要登录一次才能看");
        status.setTextColor(Ui.WARN);
        new AlertDialog.Builder(this)
                .setTitle("需要登录超星")
                .setMessage(why + "\n\n点【去登录】在下面的页面里登录一次，登录完会自动回到这里。")
                .setPositiveButton("去登录", (d, w) -> {
                    Intent i = new Intent(this, LoginActivity.class);
                    i.putExtra("link", link);
                    i.putExtra("room", room);
                    startActivityForResult(i, REQ_LOGIN);
                })
                .setNegativeButton("取消", null)
                .show();
    }

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        super.onActivityResult(req, res, data);
        if (req != REQ_LOGIN) {
            return;
        }
        if (res != RESULT_OK || data == null) {
            status.setText("没有登录，先看不了画面");
            status.setTextColor(Ui.DIM);
            return;
        }
        String room = data.getStringExtra("room");
        Streams s = Streams.fromJson(data.getStringExtra("streams"));
        if (room != null && s.ok()) {
            openPlayer(room, s);
        } else {
            status.setText("登录了，但没读到画面地址");
            status.setTextColor(Ui.WARN);
        }
    }

    private EditText input(String hint, String value, boolean secret) {
        EditText e = new EditText(this);
        e.setHint(hint);
        e.setText(value == null ? "" : value);
        e.setTextColor(Ui.TEXT);
        e.setHintTextColor(Ui.DIM);
        e.setInputType(secret
                ? InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD
                : InputType.TYPE_CLASS_TEXT);
        e.setBackgroundTintList(android.content.res.ColorStateList.valueOf(Ui.ACCENT));
        e.setPadding(dp(4), dp(10), dp(4), dp(10));
        return e;
    }

    private void addRoomDialog() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(20), dp(6), dp(20), 0);
        EditText name = input("教室名，比如 A303", "", false);
        EditText link = input("直播页链接（psp-zelda…/vri-zelda/index?speechid=…）", "", false);
        link.setTextSize(12);
        box.addView(name);
        box.addView(link);
        TextView tip = Ui.text(this, "从电脑版 rooms.json 里复制，或者直接在浏览器里打开直播页复制地址。", 11, Ui.DIM, false);
        tip.setPadding(0, dp(6), 0, 0);
        box.addView(tip);

        new AlertDialog.Builder(this)
                .setTitle("添加教室")
                .setView(box)
                .setPositiveButton("保存", (d, w) -> {
                    String n = name.getText().toString().trim();
                    String u = link.getText().toString().trim();
                    if (n.isEmpty()) {
                        toast("教室名不能空着");
                        return;
                    }
                    String problem = Store.linkProblem(u);
                    if (problem != null) {
                        toast(problem);
                        return;
                    }
                    Store.addRoom(this, n, u);
                    reload();
                    status.setText("已添加 " + n + "，点它就能看");
                    status.setTextColor(Ui.OK);
                })
                .setNegativeButton("取消", null)
                .show();
    }

    private void confirmRemove(final String room) {
        int n = Store.linkCount(this, room);
        new AlertDialog.Builder(this)
                .setTitle("删掉 " + room + "？")
                .setMessage(n > 1 ? ("这间教室有 " + n + " 个链接，会一起删掉。") : "删掉以后可以从【添加教室】再加回来。")
                .setPositiveButton("删掉", (d, w) -> {
                    Store.removeRoom(this, room);
                    reload();
                })
                .setNegativeButton("留着", null)
                .show();
    }

    private void settingsDialog() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(20), dp(6), dp(20), 0);
        TextView tip = Ui.text(this,
                "填上超星手机号和密码，取画面时会自动登录。两个都留空＝清除账号，改用网页登录（点教室时会问你）。",
                12, Ui.DIM, false);
        box.addView(tip);
        EditText user = input("手机号 / 工号", Store.user(this), false);
        EditText pass = input("密码", Store.password(this), true);
        int top = dp(8);
        user.setPadding(dp(4), top, dp(4), top);
        box.addView(user);
        box.addView(pass);
        TextView clearAcc = Ui.text(this, "清除已保存的账号密码", 13, Ui.ACCENT, false);
        clearAcc.setPadding(0, dp(12), 0, dp(4));
        clearAcc.setOnClickListener(v -> {
            Store.setAccount(this, "", "");
            user.setText("");
            pass.setText("");
            status.setText("账号已清除，下次点教室会用网页登录");
            status.setTextColor(Ui.OK);
        });
        box.addView(clearAcc);

        TextView ver = Ui.text(this, "智播课堂 Live 手机版 v1.2", 11, Ui.DIM, false);
        ver.setPadding(0, dp(10), 0, 0);
        box.addView(ver);

        new AlertDialog.Builder(this)
                .setTitle("账号设置")
                .setView(box)
                .setPositiveButton("保存", (d, w) -> {
                    Store.setAccount(this, user.getText().toString(), pass.getText().toString());
                    status.setText(Store.hasAccount(this) ? "账号已保存，下次取画面会自动登录" : "账号已清空");
                    status.setTextColor(Ui.OK);
                })
                .setNeutralButton("清除登录状态", (d, w) -> clearLogin())
                .setNegativeButton("取消", null)
                .show();
    }

    private void clearLogin() {
        try {
            CookieManager.getInstance().removeAllCookies(null);
            CookieManager.getInstance().flush();
            WebStorage.getInstance().deleteAllData();
        } catch (Exception ignored) {
        }
        status.setText("登录状态已清除，下次会重新登录");
        status.setTextColor(Ui.OK);
        toast("已清除浏览器登录状态");
    }

    private void toast(String s) {
        Toast.makeText(this, s, Toast.LENGTH_SHORT).show();
    }

    private final class RoomAdapter extends BaseAdapter {

        @Override
        public int getCount() {
            return names.size();
        }

        @Override
        public Object getItem(int position) {
            return names.get(position);
        }

        @Override
        public long getItemId(int position) {
            return position;
        }

        @Override
        public View getView(int position, View convertView, ViewGroup parent) {
            LinearLayout row;
            TextView nameView;
            TextView subView;
            if (convertView instanceof LinearLayout && convertView.getTag() != null) {
                row = (LinearLayout) convertView;
                nameView = (TextView) row.getChildAt(0);
                subView = (TextView) row.getChildAt(1);
            } else {
                row = new LinearLayout(MainActivity.this);
                row.setOrientation(LinearLayout.VERTICAL);
                row.setBackgroundResource(R.drawable.bg_card);
                row.setPadding(dp(16), dp(13), dp(16), dp(13));
                row.setLayoutParams(new AbsListView.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
                nameView = Ui.text(MainActivity.this, "", 17, Ui.TEXT, true);
                subView = Ui.text(MainActivity.this, "", 12, Ui.DIM, false);
                subView.setPadding(0, dp(3), 0, 0);
                row.addView(nameView);
                row.addView(subView);
                row.setTag("row");
            }
            String room = names.get(position);
            nameView.setText(room);
            StringBuilder sb = new StringBuilder();
            int n = Store.linkCount(MainActivity.this, room);
            sb.append(n).append(" 个链接");
            if (room.equals(Store.lastRoom(MainActivity.this))) {
                sb.append(" · 上次看的");
            }
            if (Store.cachedStream(MainActivity.this, room) != null) {
                sb.append(" · 有缓存地址");
            }
            subView.setText(sb.toString());
            return row;
        }
    }
}
