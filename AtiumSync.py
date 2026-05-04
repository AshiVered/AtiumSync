import wx
import subprocess
import threading
import re
import os
import time
import quopri

# ── Files──────────────────────────────────────────────
VCF_FILE       = "pb.vcf"
IN_CALLS       = "ich.vcf"
OUT_CALLS      = "och.vcf"
MISSED_CALLS   = "mch.vcf"
COMBINED_CALLS = "cch.vcf"

# ═══════════════════════════════════════════════════════════════════════
# Logic and parser
# ═══════════════════════════════════════════════════════════════════════

def qp_decode(s: str) -> str:
    joined = re.sub(r"=\r?\n[ \t]?", "", s)
    try:
        return quopri.decodestring(joined.encode("latin-1")).decode("utf-8", errors="replace")
    except Exception:
        return joined

def extract_qp_name(raw_value: str) -> str:
    val = raw_value.strip()
    val = re.sub(r"=\r?\n[ \t]?", "", val)  # unfold QP line continuations

    high_byte_re = re.compile(r"=[89A-Fa-f][0-9A-Fa-f]")
    qp_token = None
    for token in val.split(";"):
        if high_byte_re.search(token):
            qp_token = token
            break

    if not qp_token:
        return ""

    m = high_byte_re.search(qp_token)
    if m:
        qp_token = qp_token[m.start():]

    decoded = qp_decode(qp_token.rstrip()) if qp_token else ""
    return re.sub(r"\s{2,}", " ", decoded).strip()


def decode_contact_name(raw_value: str) -> str:
    val = raw_value.strip()
    decoded = qp_decode(val)  
    parts = decoded.split(";")
    for part in parts:
        part = part.strip()
        if part and part not in ("2.1", "3.0", "4.0"):
            return re.sub(r"\s{2,}", " ", part).strip()
    return ""

def parse_vcf_contacts(filename: str) -> list[tuple[str, str]]:
    results = []
    if not os.path.exists(filename):
        return results
    with open(filename, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read()
    unfolded = re.sub(r"=\r?\n[ \t]?", "", raw)
    unfolded = re.sub(r"\r?\n[ \t]", "", unfolded)
    for card_raw in unfolded.split("BEGIN:VCARD"):
        if not card_raw.strip():
            continue
        name, phone = "", ""
        lines = [l.strip() for l in card_raw.splitlines() if l.strip()]
        for line in lines:
            if re.match(r"TEL\b", line, re.I):
                m = re.search(r":([0-9\+\*#]+)", line)
                if m: phone = m.group(1); break
        if not phone:
            for line in lines:
                if re.match(r"N[;:]", line, re.I) and "TEL" in line.upper():
                    m = re.search(r"TEL[^:]*:([0-9\+\*#]+)", line, re.I)
                    if m: phone = m.group(1); break
        if not phone: continue

        for prefix in (r"FN[;:]", r"N[;:]"):
            if name: break
            for line in lines:
                if not re.match(prefix, line, re.I) or re.search(r"\bTEL[;:]", line, re.I):
                    continue
                colon = line.find(":")
                if colon == -1: continue
                raw_val = line[colon + 1:]
                is_qp = "QUOTED-PRINTABLE" in line.upper() or "ENCODING=" in line.upper()
                candidate = decode_contact_name(raw_val) if is_qp else re.sub(r";+", " ", raw_val).strip()
                if candidate and candidate not in ("2.1", "3.0", "4.0"):
                    name = candidate
                    break
        display_name = ("\u200f" + name) if name else "\u200fUnknown Number"
        results.append((display_name, phone))
    return results

def parse_call_log_vcf(filename: str) -> list[tuple[str, str, str]]:
    results = []
    if not os.path.exists(filename):
        return results
    with open(filename, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read()
    unfolded = re.sub(r"=\r?\n[ \t]?", "", raw)
    unfolded = re.sub(r"\r?\n[ \t]", "", unfolded)
    for card_raw in unfolded.split("BEGIN:VCARD"):
        if not card_raw.strip():
            continue
        name, phone, call_type = "", "", "Unknown"
        lines = [l.strip() for l in card_raw.splitlines() if l.strip()]

        # Extract phone number
        for line in lines:
            if re.match(r"TEL\b", line, re.I):
                m = re.search(r":([0-9\+\*#]+)", line)
                if m: phone = m.group(1); break

        if not phone:
            for line in lines:
                if re.match(r"N[;:]", line, re.I) and "TEL" in line.upper():
                    m = re.search(r"TEL[^:]*:([0-9\+\*#]+)", line, re.I)
                    if m: phone = m.group(1); break

        # Extract call type
        for line in lines:
            if line.upper().startswith("X-IRMC-CALL-DATETIME"):
                u = line.upper()
                if "RECEIVED" in u: call_type = "Incoming"
                elif "DIALED" in u: call_type = "Outgoing"
                elif "MISSED" in u: call_type = "Missed"
                else: call_type = "Rejected"
                break

        for prefix in (r"FN[;:]", r"N[;:]"):
            if name: break
            for line in lines:
                if not re.match(prefix, line, re.I):
                    continue
                if re.search(r"\bTEL[;:]", line, re.I):
                    continue
                colon = line.find(":")
                if colon == -1: continue
                raw_val = line[colon + 1:]
                is_qp = "QUOTED-PRINTABLE" in line.upper() or "ENCODING=" in line.upper()
                if is_qp:
                    candidate = extract_qp_name(raw_val)
                else:
                    candidate = re.sub(r";+", " ", raw_val).strip()
                if candidate and candidate not in ("2.1", "3.0", "4.0"):
                    name = candidate
                    break

        display_name = ""
        if not phone and not name:
            display_name = "\u200fPrivate Number"  # No phone and no name -> Private Number
        elif not name:
            display_name = "\u200fUnknown Number"  # Phone present, but no name -> Unknown Number
        else:
            display_name = "\u200f" + name

        results.append((display_name, phone, call_type))
    return results

def scan_devices() -> dict:
    devices = {}
    proc = subprocess.Popen(["bluetoothctl"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    proc.stdin.write("scan on\n"); proc.stdin.flush()
    time.sleep(5)
    proc.stdin.write("scan off\ndevices\nexit\n"); proc.stdin.flush()
    out = proc.communicate()[0]
    for line in out.splitlines():
        m = re.search(r"Device ([0-9A-F:]{17}) (.+)", line)
        if m:
            mac, name = m.groups()
            devices[mac] = name
    return devices

def fetch_data_logic(mac: str, remote_path: str):
    subprocess.run(["obexftp", "--bluetooth", mac, "--channel", "6", "-g", remote_path])

# ═══════════════════════════════════════════════════════════════════════
# GUI
# ═══════════════════════════════════════════════════════════════════════

class BluetoothApp(wx.Frame):
    def __init__(self, parent):
        super().__init__(parent, title="AtiumSync", size=(1100, 750))
        
        self.font_heb = wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, False, "Arial")
        self.font_title = wx.Font(36, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False, "Arial")
        
        main_panel = wx.Panel(self)
        main_layout = wx.BoxSizer(wx.VERTICAL)
        
        # Header
        header = wx.StaticText(main_panel, label="AtiumSync")
        header.SetFont(self.font_title)
        main_layout.Add(header, 0, wx.ALIGN_CENTER | wx.TOP | wx.BOTTOM, 20)
        
        # Content
        middle_layout = wx.BoxSizer(wx.HORIZONTAL)
        
        self.container = wx.Simplebook(main_panel)
        middle_layout.Add(self.container, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 15)
        
        sidebar = wx.BoxSizer(wx.VERTICAL)
        self.btn_goto_contacts = self._create_side_button(main_panel, "Contacts\n👤")
        self.btn_goto_calls = self._create_side_button(main_panel, "Call Logs\n📞")
        self.btn_goto_scan = self._create_side_button(main_panel, "Home / Scan\n🏠")
        
        sidebar.Add(self.btn_goto_scan, 0, wx.BOTTOM, 10)
        sidebar.Add(self.btn_goto_contacts, 0, wx.BOTTOM, 10)
        sidebar.Add(self.btn_goto_calls, 0, wx.BOTTOM, 10)
        
        middle_layout.Add(sidebar, 0, wx.EXPAND | wx.RIGHT, 15)
        main_layout.Add(middle_layout, 1, wx.EXPAND)
        
        # Footer
        footer = wx.StaticText(main_panel, label="AtiumSync V0.2 by Ashi Vered")
        main_layout.Add(footer, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        
        main_panel.SetSizer(main_layout)
        self._setup_pages()
        
        self.btn_goto_scan.Bind(wx.EVT_BUTTON, lambda e: self.container.SetSelection(0))
        self.btn_goto_contacts.Bind(wx.EVT_BUTTON, lambda e: self.container.SetSelection(1))
        self.btn_goto_calls.Bind(wx.EVT_BUTTON, lambda e: self.container.SetSelection(2))
        
        self.Center()

    def _create_side_button(self, parent, label):
        btn = wx.Button(parent, label=label, size=(180, 100))
        btn.SetFont(wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, False, "Arial"))
        return btn

    def _setup_pages(self):
        # Scan Page
        self.page_scan = wx.Panel(self.container)
        scan_sizer = wx.BoxSizer(wx.VERTICAL)
        self.listbox = wx.ListBox(self.page_scan, style=wx.LB_SINGLE)
        self.listbox.SetFont(self.font_heb)
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_scan = wx.Button(self.page_scan, label="Scan Devices", size=(150, 40))
        self.btn_sync = wx.Button(self.page_scan, label="Connect & Sync", size=(150, 40))
        self.btn_sync.SetBackgroundColour(wx.Colour("#4CAF50"))
        self.btn_sync.SetForegroundColour(wx.WHITE)
        btn_row.Add(self.btn_scan, 0, wx.RIGHT, 10)
        btn_row.Add(self.btn_sync, 0, wx.RIGHT, 10)
        scan_sizer.Add(self.listbox, 1, wx.EXPAND | wx.BOTTOM, 10)
        scan_sizer.Add(btn_row, 0, wx.ALIGN_LEFT)
        self.page_scan.SetSizer(scan_sizer)
        
        # Contacts Page
        self.page_contacts = wx.Panel(self.container)
        cont_sizer = wx.BoxSizer(wx.VERTICAL)
        self.tree_contacts = self._make_listctrl(self.page_contacts, (("N", "P"), ("Name", "Phone")))
        cont_sizer.Add(self.tree_contacts, 1, wx.EXPAND)
        self.page_contacts.SetSizer(cont_sizer)
        
        # Calls Page
        self.page_calls = wx.Panel(self.container)
        calls_main_sizer = wx.BoxSizer(wx.VERTICAL)
        self.call_tabs = wx.Notebook(self.page_calls)
        self.trees = {"contacts": self.tree_contacts}
        tab_specs = [("all", "All"), ("missed", "Missed"), ("in", "Incoming"), ("out", "Outgoing"), ("rejected", "Rejected")]
        
        for key, label in tab_specs:
            p = wx.Panel(self.call_tabs)
            cols = ("N", "P", "T") if key == "all" else ("N", "P")
            heads = ("Name", "Phone", "Type") if key == "all" else ("Name", "Phone")
            self.trees[key] = self._make_listctrl(p, (cols, heads))
            p_sizer = wx.BoxSizer(wx.VERTICAL)
            p_sizer.Add(self.trees[key], 1, wx.EXPAND)
            p.SetSizer(p_sizer)
            self.call_tabs.AddPage(p, label)
            
        calls_main_sizer.Add(self.call_tabs, 1, wx.EXPAND)
        self.page_calls.SetSizer(calls_main_sizer)
        
        # Add to container
        self.container.AddPage(self.page_scan, "Scan")
        self.container.AddPage(self.page_contacts, "Contacts")
        self.container.AddPage(self.page_calls, "Calls")
        
        self.btn_scan.Bind(wx.EVT_BUTTON, self.start_scan)
        self.btn_sync.Bind(wx.EVT_BUTTON, self.start_fetch)

    def _make_listctrl(self, parent, spec) -> wx.ListCtrl:
        cols, heads = spec
        lc = wx.ListCtrl(parent, style=wx.LC_REPORT | wx.LC_VRULES | wx.LC_HRULES)
        lc.SetFont(self.font_heb)
        for i, (col, head) in enumerate(zip(cols, heads)):
            w = 120 if col == "T" else (350 if col == "N" else 200)
            lc.InsertColumn(i, head, width=w)
        return lc

    def start_scan(self, event=None):
        def worker():
            devs = scan_devices()
            wx.CallAfter(self._update_scan_list, devs)
        threading.Thread(target=worker, daemon=True).start()

    def _update_scan_list(self, devs):
        self.listbox.Clear()
        for mac, name in devs.items():
            self.listbox.Append(f"{name} ({mac})")

    def start_fetch(self, event=None):
        selections = self.listbox.GetSelections()
        if not selections:
            wx.MessageBox("Please select a device first", "Error", wx.OK | wx.ICON_WARNING)
            return
        item_text = self.listbox.GetString(selections[0])
        mac = item_text.split("(")[-1].replace(")", "")
        pairs = [("telecom/pb.vcf", VCF_FILE), ("telecom/ich.vcf", IN_CALLS), ("telecom/och.vcf", OUT_CALLS), ("telecom/mch.vcf", MISSED_CALLS), ("telecom/cch.vcf", COMBINED_CALLS)]
        def worker():
            for remote, local in pairs:
                fetch_data_logic(mac, remote)
                time.sleep(1.0)
            wx.CallAfter(self._on_sync_done)
        threading.Thread(target=worker, daemon=True).start()

    def _on_sync_done(self):
        self.load_data()
        wx.MessageBox("Sync Completed Successfully!", "Done ✓", wx.OK | wx.ICON_INFORMATION)

    def load_data(self):
        for t in self.trees.values(): t.DeleteAllItems()
        file_map_contacts = [(VCF_FILE, "contacts")]
        for vcf_file, key in file_map_contacts:
            for name, phone in parse_vcf_contacts(vcf_file):
                idx = self.trees[key].GetItemCount()
                self.trees[key].InsertItem(idx, name); self.trees[key].SetItem(idx, 1, phone)
        
        file_map_calls = [(IN_CALLS, "in"), (OUT_CALLS, "out"), (MISSED_CALLS, "missed")]
        for vcf_file, key in file_map_calls:
            for name, phone, _ in parse_call_log_vcf(vcf_file):
                idx = self.trees[key].GetItemCount()
                self.trees[key].InsertItem(idx, name); self.trees[key].SetItem(idx, 1, phone)

        if os.path.exists(COMBINED_CALLS):
            for name, phone, call_type in parse_call_log_vcf(COMBINED_CALLS):
                idx = self.trees["all"].GetItemCount()
                self.trees["all"].InsertItem(idx, name); self.trees["all"].SetItem(idx, 1, phone); self.trees["all"].SetItem(idx, 2, call_type)
                if call_type == "Rejected":
                    idx_rej = self.trees["rejected"].GetItemCount()
                    self.trees["rejected"].InsertItem(idx_rej, name); self.trees["rejected"].SetItem(idx_rej, 1, phone)

if __name__ == "__main__":
    app = wx.App(False)
    frame = BluetoothApp(None)
    frame.Show()
    app.MainLoop()
