package kg.zoobase.platform;

import android.app.*;
import android.content.*;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.os.Build;
import java.text.SimpleDateFormat;
import java.util.*;

/** Daily local reminder. No Python process, server, network or exact-alarm permission needed. */
public final class ReminderReceiver extends BroadcastReceiver {
    private static final String CHANNEL = "zoobase_tasks";
    private static PendingIntent alarm(Context c) {
        return PendingIntent.getBroadcast(c, 73, new Intent(c, ReminderReceiver.class),
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }
    public static void configure(Context c, String database, String language, boolean enabled) {
        c.getSharedPreferences("reminders", 0).edit().putString("db", database)
            .putString("lang", language).putBoolean("enabled", enabled).apply();
        NotificationManager nm = (NotificationManager)c.getSystemService(Context.NOTIFICATION_SERVICE);
        nm.createNotificationChannel(new NotificationChannel(CHANNEL, "ZooBase", NotificationManager.IMPORTANCE_DEFAULT));
        nm.cancel(73);
        schedule(c);
    }
    private static void schedule(Context c) {
        AlarmManager manager = (AlarmManager)c.getSystemService(Context.ALARM_SERVICE);
        manager.cancel(alarm(c));
        if (!c.getSharedPreferences("reminders", 0).getBoolean("enabled", false)) return;
        Calendar next = Calendar.getInstance();
        next.set(Calendar.HOUR_OF_DAY, 8); next.set(Calendar.MINUTE, 0); next.set(Calendar.SECOND, 0);
        if (next.getTimeInMillis() <= System.currentTimeMillis()) next.add(Calendar.DAY_OF_YEAR, 1);
        manager.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, next.getTimeInMillis(), alarm(c));
    }
    @Override public void onReceive(Context c, Intent intent) {
        SharedPreferences prefs = c.getSharedPreferences("reminders", 0);
        if (!prefs.getBoolean("enabled", false)) return;
        schedule(c);
        if (Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) return;
        try (SQLiteDatabase database = SQLiteDatabase.openDatabase(prefs.getString("db", ""), null, SQLiteDatabase.OPEN_READONLY)) {
            String today = new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(new Date());
            try (Cursor rows = database.rawQuery("SELECT COUNT(*) FROM task WHERE done=0 AND due_date<=? AND farm_id=(SELECT MIN(id) FROM farm)", new String[]{today})) {
                if (!rows.moveToFirst() || rows.getInt(0) == 0) return;
                boolean ky = "ky".equals(prefs.getString("lang", "ky"));
                String message = (ky ? "Бүгүнкү жана мөөнөтү өткөн тапшырмалар: " : "Сегодня и просрочено задач: ") + rows.getInt(0);
                Intent launch = c.getPackageManager().getLaunchIntentForPackage(c.getPackageName());
                PendingIntent open = PendingIntent.getActivity(c, 74, launch, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
                Notification notification = new Notification.Builder(c, CHANNEL)
                    .setSmallIcon(android.R.drawable.ic_popup_reminder).setContentTitle("ZooBase")
                    .setContentText(message).setContentIntent(open).setAutoCancel(true).build();
                NotificationManager nm = (NotificationManager)c.getSystemService(Context.NOTIFICATION_SERVICE);
                if (nm.areNotificationsEnabled()) nm.notify(73, notification);
            }
        } catch (Exception error) {
            android.util.Log.e("ZooBase", "Cannot read local reminders", error);
        }
    }
}
