package com.zufe.liveview;

import org.json.JSONObject;

/** 一路直播的画面：课堂摄像头(main)、电脑桌面(ppt)、教室全景(other)，外加 AI 转写要用的参数。 */
public class Streams {

    public String main = "";
    public String ppt = "";
    /** 教室后方/全景机位（args.videos 里 type=other 那一路）。 */
    public String other = "";
    public String course = "";
    public String enc = "";
    public String fid = "";
    public String speechid = "";

    public boolean ok() {
        return main != null && main.trim().length() > 0;
    }

    public JSONObject toJson() {
        JSONObject o = new JSONObject();
        try {
            o.put("main", main == null ? "" : main);
            o.put("ppt", ppt == null ? "" : ppt);
            o.put("other", other == null ? "" : other);
            o.put("course", course == null ? "" : course);
            o.put("enc", enc == null ? "" : enc);
            o.put("fid", fid == null ? "" : fid);
            o.put("speechid", speechid == null ? "" : speechid);
            o.put("at", System.currentTimeMillis());
        } catch (Exception ignored) {
        }
        return o;
    }

    public static Streams fromJson(String s) {
        Streams st = new Streams();
        if (s == null) {
            return st;
        }
        try {
            JSONObject o = new JSONObject(s);
            st.main = nz(o.optString("main", ""));
            st.ppt = nz(o.optString("ppt", ""));
            st.other = nz(o.optString("other", ""));
            st.course = nz(o.optString("course", ""));
            st.enc = nz(o.optString("enc", ""));
            st.fid = nz(o.optString("fid", ""));
            st.speechid = nz(o.optString("speechid", ""));
        } catch (Exception ignored) {
        }
        return st;
    }

    private static String nz(String s) {
        return s == null ? "" : s;
    }
}
