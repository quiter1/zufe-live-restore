package com.zufe.liveview;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;

/** 教室表、上次看的教室、账号、每间教室上一次取到的画面地址，都在这里。 */
public final class Store {

    private static final String PREF = "liveview";
    private static final String K_ROOMS = "rooms";
    private static final String K_LAST = "lastRoom";
    private static final String K_USER = "user";
    private static final String K_PASS = "pass";
    private static final String K_CACHE = "cache:";

    private Store() {
    }

    private static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences(PREF, Context.MODE_PRIVATE);
    }

    /** 第一次打开时，把电脑版那 16 间教室灌进来。 */
    public static synchronized void init(Context c) {
        SharedPreferences p = prefs(c);
        if (p.contains(K_ROOMS)) {
            return;
        }
        String fallback = "{}";
        try {
            InputStream in = c.getAssets().open("rooms.json");
            ByteArrayOutputStream bo = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) {
                bo.write(buf, 0, n);
            }
            in.close();
            JSONObject o = new JSONObject(new String(bo.toByteArray(), "UTF-8"));
            fallback = o.toString();
        } catch (Exception ignored) {
        }
        p.edit().putString(K_ROOMS, fallback).apply();
    }

    public static JSONObject rooms(Context c) {
        try {
            return new JSONObject(prefs(c).getString(K_ROOMS, "{}"));
        } catch (Exception e) {
            return new JSONObject();
        }
    }

    private static void saveRooms(Context c, JSONObject o) {
        prefs(c).edit().putString(K_ROOMS, o.toString()).apply();
    }

    public static List<String> roomNames(Context c) {
        List<String> out = new ArrayList<>();
        JSONObject o = rooms(c);
        Iterator<String> it = o.keys();
        while (it.hasNext()) {
            out.add(it.next());
        }
        Collections.sort(out, ROOM_ORDER);
        return out;
    }

    /** 和电脑版一样：先按字母，再按数字，9107 这种纯数字排最前面。 */
    public static final Comparator<String> ROOM_ORDER = new Comparator<String>() {
        @Override
        public int compare(String a, String b) {
            int[] x = key(a);
            int[] y = key(b);
            if (x[0] != y[0]) {
                return x[0] < y[0] ? -1 : 1;
            }
            if (x[1] != y[1]) {
                return x[1] < y[1] ? -1 : 1;
            }
            return a.compareToIgnoreCase(b);
        }

        private int[] key(String s) {
            String up = s.trim().toUpperCase(Locale.ROOT);
            int i = 0;
            while (i < up.length() && Character.isLetter(up.charAt(i))) {
                i++;
            }
            int j = i;
            while (j < up.length() && Character.isDigit(up.charAt(j))) {
                j++;
            }
            int rank = 0;
            for (int k = 0; k < i; k++) {
                rank = rank * 26 + (up.charAt(k) - 'A' + 1);
            }
            int num;
            try {
                num = j > i ? Integer.parseInt(up.substring(i, j)) : 0;
            } catch (NumberFormatException e) {
                num = 0;
            }
            return new int[]{rank, num};
        }
    };

    private static JSONArray links(Context c, String room) {
        JSONObject o = rooms(c);
        Object v = o.opt(room);
        if (v instanceof JSONArray) {
            return (JSONArray) v;
        }
        JSONArray a = new JSONArray();
        if (v instanceof String) {
            a.put((String) v);
        }
        return a;
    }

    public static int linkCount(Context c, String room) {
        return links(c, room).length();
    }

    public static String firstLink(Context c, String room) {
        JSONArray a = links(c, room);
        for (int i = 0; i < a.length(); i++) {
            String u = normalize(a.optString(i, ""));
            if (u.length() > 0) {
                return u;
            }
        }
        return null;
    }

    /** 手机版链接统一成 index 页面。 */
    public static String normalize(String link) {
        if (link == null) {
            return "";
        }
        String s = link.trim();
        s = s.replaceAll("(?i)/vri-zelda/mobile_live", "/vri-zelda/index");
        return s;
    }

    /** 返回 null 表示没问题，否则返回原因。 */
    public static String linkProblem(String link) {
        String s = normalize(link);
        if (s.isEmpty()) {
            return "直播链接不能为空";
        }
        if (!s.startsWith("http://") && !s.startsWith("https://")) {
            return "链接要以 http:// 或 https:// 开头";
        }
        if (!s.contains("speechid=")) {
            return "链接里没有 speechid，请把直播页面完整地址复制过来";
        }
        return null;
    }

    public static void addRoom(Context c, String name, String link) {
        String n = name.trim();
        if (n.isEmpty()) {
            return;
        }
        String u = normalize(link);
        JSONObject o = rooms(c);
        JSONArray a = links(c, n);
        boolean dup = false;
        for (int i = 0; i < a.length(); i++) {
            if (u.equals(normalize(a.optString(i, "")))) {
                dup = true;
            }
        }
        if (!dup && u.length() > 0) {
            a.put(u);
        }
        try {
            o.put(n, a);
        } catch (Exception ignored) {
        }
        saveRooms(c, o);
    }

    public static void removeRoom(Context c, String room) {
        JSONObject o = rooms(c);
        o.remove(room);
        saveRooms(c, o);
        prefs(c).edit().remove(K_CACHE + room).apply();
    }

    public static String lastRoom(Context c) {
        return prefs(c).getString(K_LAST, "");
    }

    public static void setLastRoom(Context c, String room) {
        prefs(c).edit().putString(K_LAST, room).apply();
    }

    public static String user(Context c) {
        return prefs(c).getString(K_USER, "").trim();
    }

    public static String password(Context c) {
        return prefs(c).getString(K_PASS, "");
    }

    public static void setAccount(Context c, String user, String pass) {
        prefs(c).edit().putString(K_USER, user == null ? "" : user.trim())
                .putString(K_PASS, pass == null ? "" : pass).apply();
    }

    public static boolean hasAccount(Context c) {
        return user(c).length() > 0 && password(c).length() > 0;
    }

    public static void saveStream(Context c, String room, Streams s) {
        if (s == null || !s.ok()) {
            return;
        }
        prefs(c).edit().putString(K_CACHE + room, s.toJson().toString()).apply();
    }

    public static Streams cachedStream(Context c, String room) {
        String raw = prefs(c).getString(K_CACHE + room, "");
        if (raw.isEmpty()) {
            return null;
        }
        Streams s = Streams.fromJson(raw);
        return s.ok() ? s : null;
    }

    public static long cachedAt(Context c, String room) {
        String raw = prefs(c).getString(K_CACHE + room, "");
        if (raw.isEmpty()) {
            return 0;
        }
        try {
            return new JSONObject(raw).optLong("at", 0);
        } catch (Exception e) {
            return 0;
        }
    }
}
