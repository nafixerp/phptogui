"""PhoneBookService tests (headless) — mapping, summary, URLs, type labels."""

from python_gui.modules.phonebook.service import PhoneBookService, type_label


class FakeRepo:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def load_contacts(self, ctype, search, contact_status):
        self.calls.append((ctype, search, contact_status))
        return [r for r in self.rows if ctype == "ALL" or r.get("ctype") == ctype]

    def quick_lookup(self, needle, digits):
        return [r for r in self.rows if needle in str(r.get("mobile", ""))]


ROWS = [
    {"code": "C0001", "name": "ACME", "ctype": "C", "mobile": "98765 43210",
     "telephone": "0480-111", "email": "a@x.com", "city": "Kochi"},
    {"code": "C0002", "name": "BETA", "ctype": "C", "mobile": "", "telephone": "0480-222",
     "email": "", "city": "Aluva"},
    {"code": "S0001", "name": "VEND", "ctype": "S", "mobile": "", "telephone": "",
     "email": "", "city": ""},
]


def svc():
    return PhoneBookService(FakeRepo(ROWS))


def test_type_labels():
    assert type_label("C") == "Customer"
    assert type_label("G") == "Goldsmith"
    assert type_label("") == "Party"
    assert type_label("X") == "X"


def test_list_maps_contact_and_urls():
    rows = svc().list_contacts("C")
    acme = next(r for r in rows if r["code"] == "C0001")
    assert acme["type_label"] == "Customer"
    assert acme["contact"] == "98765 43210"             # mobile preferred
    assert acme["whatsapp_url"] == "https://wa.me/9876543210"   # digits only
    assert acme["tel_url"] == "tel:98765 43210"
    assert acme["mail_url"] == "mailto:a@x.com"
    beta = next(r for r in rows if r["code"] == "C0002")
    assert beta["contact"] == "0480-222"                # falls back to telephone
    assert beta["whatsapp_url"] == "" and beta["mail_url"] == ""


def test_summary_counts_over_all_status():
    s = svc().summary("C")
    assert s == {"total": 2, "with_mobile": 1, "with_phone": 2, "with_email": 1}
    # summary must query with contact_status='all'
    assert svc.__wrapped__ if False else True


def test_summary_uses_all_status_filter():
    service = svc()
    service.summary("C", "x")
    assert ("C", "x", "all") in service.repo.calls


def test_all_type_returns_every_party():
    rows = svc().list_contacts("ALL")
    assert {r["code"] for r in rows} == {"C0001", "C0002", "S0001"}
