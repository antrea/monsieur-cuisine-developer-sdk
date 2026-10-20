package org.blackstufflabs.monsieurcuisine.manager;

import android.database.Cursor;
import android.database.MatrixCursor;
import android.os.CancellationSignal;
import android.os.ParcelFileDescriptor;
import android.provider.DocumentsContract.Document;
import android.provider.DocumentsContract.Root;
import android.provider.DocumentsProvider;
import java.io.File;
import java.io.FileNotFoundException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** Test-only SAF provider serving supplied, independent developer APKs.
 * Not packaged in the Manager, no OEM content, no external storage permission.
 * Documents: the legacy ``files/consent-fixture.apk`` plus every ``*.apk`` in
 * ``files/fixtures``; the display name is the file name. A software provider
 * demonstrates the Manager flow, never the mounting of a physical USB drive.
 */
public final class FixtureDocumentsProvider extends DocumentsProvider {
    private static final String[] ROOT_COLUMNS = {Root.COLUMN_ROOT_ID, Root.COLUMN_DOCUMENT_ID,
        Root.COLUMN_TITLE, Root.COLUMN_FLAGS, Root.COLUMN_MIME_TYPES};
    private static final String[] DOCUMENT_COLUMNS = {Document.COLUMN_DOCUMENT_ID, Document.COLUMN_DISPLAY_NAME,
        Document.COLUMN_MIME_TYPE, Document.COLUMN_FLAGS, Document.COLUMN_SIZE};
    private static final String APK_TYPE = "application/vnd.android.package-archive";
    private static final String LEGACY = "consent-fixture.apk";

    @Override public boolean onCreate() { return true; }
    private File fixtures() { return new File(getContext().getFilesDir(), "fixtures"); }

    private List<String> documents() {
        List<String> names = new ArrayList<>();
        if (new File(getContext().getFilesDir(), LEGACY).isFile()) names.add(LEGACY);
        String[] listed = fixtures().list();
        if (listed != null) {
            Arrays.sort(listed);
            for (String name : listed) if (name.endsWith(".apk") && new File(fixtures(), name).isFile()) names.add(name);
        }
        return names;
    }

    private File resolve(String id) throws FileNotFoundException {
        if (id == null || id.contains("/") || id.contains("\\") || id.startsWith(".") || !id.endsWith(".apk")) {
            throw new FileNotFoundException("unknown test document");
        }
        File file = LEGACY.equals(id) ? new File(getContext().getFilesDir(), LEGACY) : new File(fixtures(), id);
        if (!file.isFile()) throw new FileNotFoundException("test document is not available any more");
        return file;
    }

    @Override public Cursor queryRoots(String[] projection) {
        MatrixCursor cursor = new MatrixCursor(projection == null ? ROOT_COLUMNS : projection);
        MatrixCursor.RowBuilder row = cursor.newRow();
        row.add(Root.COLUMN_ROOT_ID, "fixture"); row.add(Root.COLUMN_DOCUMENT_ID, "root");
        row.add(Root.COLUMN_TITLE, "MC SDK test APKs"); row.add(Root.COLUMN_FLAGS, Root.FLAG_LOCAL_ONLY);
        row.add(Root.COLUMN_MIME_TYPES, APK_TYPE); return cursor;
    }

    private void add(MatrixCursor cursor, String id) throws FileNotFoundException {
        MatrixCursor.RowBuilder row = cursor.newRow();
        if ("root".equals(id)) {
            row.add(Document.COLUMN_DOCUMENT_ID, id); row.add(Document.COLUMN_DISPLAY_NAME, "MC SDK test APKs");
            row.add(Document.COLUMN_MIME_TYPE, Document.MIME_TYPE_DIR); row.add(Document.COLUMN_FLAGS, 0);
            row.add(Document.COLUMN_SIZE, 0); return;
        }
        File file = resolve(id);
        row.add(Document.COLUMN_DOCUMENT_ID, id);
        row.add(Document.COLUMN_DISPLAY_NAME, LEGACY.equals(id) ? "MC SDK consent fixture.apk" : id);
        row.add(Document.COLUMN_MIME_TYPE, APK_TYPE); row.add(Document.COLUMN_FLAGS, 0);
        row.add(Document.COLUMN_SIZE, file.length());
    }

    @Override public Cursor queryDocument(String id, String[] projection) throws FileNotFoundException {
        MatrixCursor cursor = new MatrixCursor(projection == null ? DOCUMENT_COLUMNS : projection); add(cursor, id); return cursor;
    }

    @Override public Cursor queryChildDocuments(String parent, String[] projection, String order) throws FileNotFoundException {
        if (!"root".equals(parent)) throw new FileNotFoundException("unknown root");
        MatrixCursor cursor = new MatrixCursor(projection == null ? DOCUMENT_COLUMNS : projection);
        for (String id : documents()) add(cursor, id);
        return cursor;
    }

    @Override public ParcelFileDescriptor openDocument(String id, String mode, CancellationSignal signal) throws FileNotFoundException {
        if (!"r".equals(mode)) throw new FileNotFoundException("read-only test document");
        File file = resolve(id);
        // A fixture named "unreadable-*.apk" is listed but can no longer be opened: the test
        // stand-in for a USB drive removed between browsing and installation.
        if (id.startsWith("unreadable-")) throw new FileNotFoundException("test document vanished before it was read");
        return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY);
    }
}
