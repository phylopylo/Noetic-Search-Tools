import gi
from gi.repository import Gtk, GLib
import os
import threading
import fitz  # PyMuPDF
import queue
import pandas as pd
gi.require_version('Gtk', '4.0')

log_errors = False

class DocumentSearchApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='com.example.docsearch')
        self.search_queue = queue.Queue()
        self.result_queue = queue.Queue()
        
    def do_activate(self):
        # Create main window
        self.win = Gtk.ApplicationWindow(application=self)
        self.win.set_title("Document Search Tool")
        self.win.set_default_size(800, 600)
        
        # Create main vertical box
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.win.set_child(vbox)

        # Style Box
        vbox.set_margin_start(20)   # left padding
        vbox.set_margin_end(20)     # right padding
        vbox.set_margin_top(20)     # top padding
        vbox.set_margin_bottom(20)  # bottom padding

        
        # Create folder picker
        folder_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.folder_button = Gtk.Button(label="Select Folder")
        self.folder_button.connect('clicked', self.on_folder_clicked)
        self.folder_label = Gtk.Label(label="No folder selected")
        folder_box.append(self.folder_button)
        folder_box.append(self.folder_label)
        vbox.append(folder_box)
        
        # Create search entry
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.search_entry = Gtk.Entry()
        self.search_entry.set_placeholder_text("Enter search text...")
        self.search_button = Gtk.Button(label="Search")
        self.search_button.connect('clicked', self.on_search_clicked)
        search_box.append(self.search_entry)
        search_box.append(self.search_button)
        vbox.append(search_box)
        
        # Create file type checkboxes
        types_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.pdf_check = Gtk.CheckButton(label="PDF")
        self.csv_check = Gtk.CheckButton(label="CSV")
        self.excel_check = Gtk.CheckButton(label="Excel")
        self.case_sensitive_check = Gtk.CheckButton(label="Case-sensitive")
        self.pdf_check.set_active(True)
        self.csv_check.set_active(True)
        self.excel_check.set_active(True)
        types_box.append(self.pdf_check)
        types_box.append(self.csv_check)
        types_box.append(self.excel_check)
        types_box.append(self.case_sensitive_check)
        vbox.append(types_box)
        
        # Create output text view
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        self.text_view = Gtk.TextView()
        self.text_view.set_editable(False)
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.text_buffer = self.text_view.get_buffer()
        scrolled.set_child(self.text_view)
        vbox.append(scrolled)
        
        # Show the window
        self.win.present()
        
        # Start worker thread
        self.worker_thread = threading.Thread(target=self.search_worker, daemon=True)
        self.worker_thread.start()
        
        # Setup periodic check for results
        GLib.timeout_add(100, self.check_results)
    
    def on_folder_clicked(self, button):
        dialog = Gtk.FileChooserDialog(
            title="Select Folder",
            parent=self.win,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dialog.add_buttons(
            "_Cancel",
            Gtk.ResponseType.CANCEL,
            "_Select",
            Gtk.ResponseType.ACCEPT,
        )
        
        dialog.connect("response", self.on_folder_dialog_response)
        dialog.present()
    
    def on_folder_dialog_response(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            self.selected_folder = dialog.get_file().get_path()
            self.folder_label.set_text(self.selected_folder)
        dialog.destroy()
    
    def on_search_clicked(self, button):
        if not hasattr(self, 'selected_folder'):
            self.text_buffer.set_text("Please select a folder first.")
            return
        
        search_text = self.search_entry.get_text()
        if not search_text:
            self.text_buffer.set_text("Please enter search text.")
            return
        
        file_types = []
        if self.pdf_check.get_active():
            file_types.append('.pdf')
        if self.csv_check.get_active():
            file_types.append('.csv')
        if self.excel_check.get_active():
            file_types.extend(['.xls', '.xlsx', '.xlsm'])
            
        if not file_types:
            self.text_buffer.set_text("Please select at least one file type to search.")
            return
        
        case_sensitive = self.case_sensitive_check.get_active()
        self.text_buffer.set_text("Searching...")
        self.search_queue.put((self.selected_folder, search_text, file_types, case_sensitive))
    
    def search_pdf(self, pdf_path, search_text, case_sensitive):
        results = []
        try:
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                if search_text.lower() in text.lower():
                    text_lines = text.split('\n')
                    for i, line in enumerate(text_lines):
                        is_match = (search_text in line) or (search_text.lower() in line.lower() and not case_sensitive)
                        if is_match:
                            context = f"\nFile: {pdf_path}\nPage: {page_num + 1}\nLine: {i + 1}\nContext: ...{line.strip()}..."
                            results.append(context)
            doc.close()
        except Exception as e:
            if log_errors:
                results.append(f"\nError processing {pdf_path}: {str(e)}")
        return results

    def search_spreadsheet(self, file_path, search_text, case_sensitive):
        results = []
        try:
            # Determine file type and read accordingly
            if file_path.lower().endswith('.csv'):
                df = pd.read_csv(file_path)
            else:  # Excel files
                df = pd.read_excel(file_path)
            
            # Convert all columns to string type for searching
            df = df.astype(str)
            
            # Search through each cell
            for col in df.columns:
                matches = df[df[col].str.contains(search_text, case=case_sensitive, na=False)]
                if not matches.empty:
                    for idx, row in matches.iterrows():
                        context = f"\nFile: {file_path}\nColumn: {col}\nRow: {idx + 2}\nContext: {row[col]}"
                        results.append(context)
                        
        except Exception as e:
            if log_errors:
                results.append(f"\nError processing {file_path}: {str(e)}")
        return results
    
    def search_worker(self):
        while True:
            folder, search_text, file_types, case_sensitive  = self.search_queue.get()
            results = []
            
            for root, dirs, files in os.walk(folder):
                for file in files:
                    file_lower = file.lower()
                    if any(file_lower.endswith(ext.lower()) for ext in file_types):
                        file_path = os.path.join(root, file)
                        
                        if file_lower.endswith('.pdf'):
                            results.extend(self.search_pdf(file_path, search_text, case_sensitive))
                        elif file_lower.endswith(('.csv', '.xls', '.xlsx', '.xlsm')):
                            results.extend(self.search_spreadsheet(file_path, search_text, case_sensitive))
            
            self.result_queue.put(results)
    
    def check_results(self):
        try:
            results = self.result_queue.get_nowait()
            if not results:
                self.text_buffer.set_text("No results found.")
            else:
                self.text_buffer.set_text("Search Results:" + '\n\n---\n'.join(results))
        except queue.Empty:
            pass
        return True

def main():
    app = DocumentSearchApp()
    return app.run(None)

if __name__ == "__main__":
    main()
