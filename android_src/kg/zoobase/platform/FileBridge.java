package kg.zoobase.platform;

import android.content.Context;
import android.net.Uri;
import java.io.*;

/** SAF works on Android 8+ without broad storage permissions. */
public final class FileBridge {
    public static void read(Context context, String uri, String path, long limit) throws IOException {
        try (InputStream input = context.getContentResolver().openInputStream(Uri.parse(uri));
             OutputStream output = new FileOutputStream(path)) {
            copy(input, output, limit);
        }
    }
    public static void write(Context context, String path, String uri) throws IOException {
        try (InputStream input = new FileInputStream(path);
             OutputStream output = context.getContentResolver().openOutputStream(Uri.parse(uri), "wt")) {
            copy(input, output, Long.MAX_VALUE);
        }
    }
    private static void copy(InputStream input, OutputStream output, long limit) throws IOException {
        if (input == null || output == null) throw new IOException("Cannot open document");
        byte[] buffer = new byte[16384];
        long total = 0;
        int count;
        while ((count = input.read(buffer)) != -1) {
            total += count;
            if (total > limit) throw new IOException("Document too large");
            output.write(buffer, 0, count);
        }
    }
}
