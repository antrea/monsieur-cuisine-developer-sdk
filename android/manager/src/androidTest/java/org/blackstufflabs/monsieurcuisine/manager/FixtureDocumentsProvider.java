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

/** Test-only SAF provider serving one supplied, independent developer APK.
 * Not packaged in the Manager, no OEM content, no external storage permission.
 */
public final class FixtureDocumentsProvider extends DocumentsProvider {
    private static final String[] ROOT_COLUMNS = {Root.COLUMN_ROOT_ID, Root.COLUMN_DOCUMENT_ID,
        Root.COLUMN_TITLE, Root.COLUMN_FLAGS, Root.COLUMN_MIME_TYPES};
    private static final String[] DOCUMENT_COLUMNS = {Document.COLUMN_DOCUMENT_ID, Document.COLUMN_DISPLAY_NAME,
        Document.COLUMN_MIME_TYPE, Document.COLUMN_FLAGS, Document.COLUMN_SIZE};
    private static final String APK_TYPE = "application/vnd.android.package-archive";

    @Override public boolean onCreate() { return true; }
    private File fixture() { return new File(getContext().getFilesDir(), "consent-fixture.apk"); }
    @Override public Cursor queryRoots(String[] projection) {
        MatrixCursor cursor = new MatrixCursor(projection == null ? ROOT_COLUMNS : projection);
        MatrixCursor.RowBuilder row = cursor.newRow();
        row.add(Root.COLUMN_ROOT_ID, "fixture"); row.add(Root.COLUMN_DOCUMENT_ID, "root");
        row.add(Root.COLUMN_TITLE, "MC SDK test APKs"); row.add(Root.COLUMN_FLAGS, Root.FLAG_LOCAL_ONLY);
        row.add(Root.COLUMN_MIME_TYPES, APK_TYPE); return cursor;
    }
    private void add(MatrixCursor cursor, String id) throws FileNotFoundException {
        if (!("root".equals(id) || "apk".equals(id))) throw new FileNotFoundException("unknown test document");
        boolean root = "root".equals(id);
        MatrixCursor.RowBuilder row = cursor.newRow();
        row.add(Document.COLUMN_DOCUMENT_ID, id);
        row.add(Document.COLUMN_DISPLAY_NAME, root ? "MC SDK test APKs" : "MC SDK consent fixture.apk");
        row.add(Document.COLUMN_MIME_TYPE, root ? Document.MIME_TYPE_DIR : APK_TYPE);
        row.add(Document.COLUMN_FLAGS, 0); row.add(Document.COLUMN_SIZE, root ? 0 : fixture().length());
    }
    @Override public Cursor queryDocument(String id, String[] projection) throws FileNotFoundException {
        MatrixCursor cursor = new MatrixCursor(projection == null ? DOCUMENT_COLUMNS : projection); add(cursor, id); return cursor;
    }
    @Override public Cursor queryChildDocuments(String parent, String[] projection, String order) throws FileNotFoundException {
        if (!"root".equals(parent)) throw new FileNotFoundException("unknown root");
        MatrixCursor cursor = new MatrixCursor(projection == null ? DOCUMENT_COLUMNS : projection); add(cursor, "apk"); return cursor;
    }
    @Override public ParcelFileDescriptor openDocument(String id, String mode, CancellationSignal signal) throws FileNotFoundException {
        if (!"apk".equals(id) || !"r".equals(mode)) throw new FileNotFoundException("read-only test document");
        return ParcelFileDescriptor.open(fixture(), ParcelFileDescriptor.MODE_READ_ONLY);
    }
}
