import os
import io
import csv
import uuid
import base64
import smtplib
from datetime import datetime
from zoneinfo import ZoneInfo
from functools import wraps
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

import qrcode
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify, Response
)
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY", "the-white-reflection-secret-2026")

# Konfigurasi Environment Variables
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "bukti-tf")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")

supabase: Client = create_client(
    SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None


# ==========================================
# HELPER & MIDDLEWARE
# ==========================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def get_wib_now():
    return datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%d-%m-%Y %H:%M:%S WIB")


def generate_qr_base64(ticket_code: str) -> str:
    """Generate QR Code menggunakan import qrcode dan kembalikan sebagai Base64 string."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(ticket_code)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#0b291f", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def send_ticket_email(recipient_email: str, nama: str, paket: str, ticket_code: str, qr_base64: str):
    """Kirim email berisi detail tiket dan lampiran QR Code melalui Gmail SMTP."""
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        raise ValueError(
            "Konfigurasi GMAIL_USER atau GMAIL_APP_PASSWORD belum diatur di .env")

    msg = MIMEMultipart("related")
    msg["Subject"] = f"E-Ticket The White Reflection — {nama} ({paket})"
    msg["From"] = f"The White Spot X MMS <{GMAIL_USER}>"
    msg["To"] = recipient_email

    html_content = f"""
    <div style="font-family: 'Georgia', serif; max-width: 560px; margin: 0 auto; background: #050a08; color: #f4f6f5; padding: 32px; border-radius: 16px; border: 1px solid #144936;">
        <p style="color: #6ee7b7; font-size: 12px; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 8px;">
            The White Spot × Madrasah Mar'ah Shalihah
        </p>
        <h2 style="font-size: 28px; font-weight: normal; margin: 0 0 16px 0; color: #ffffff;">
            The White <em>Reflection</em>
        </h2>
        <p style="font-family: Arial, sans-serif; font-size: 14px; color: #cbd5e1; line-height: 1.6;">
            Assalamu'alaikum <strong>{nama}</strong>,<br>
            Terima kasih, pembayaran Anda untuk seminar & bedah buku <em>"Ketika Aku Marah pada Takdir"</em> telah diverifikasi oleh admin.
        </p>

        <div style="background: #0b291f; padding: 18px; border-radius: 12px; margin: 20px 0; font-family: Arial, sans-serif; font-size: 14px;">
            <p style="margin: 4px 0;"><strong>Nama Peserta:</strong> {nama}</p>
            <p style="margin: 4px 0;"><strong>Jenis Paket:</strong> Paket {paket}</p>
            <p style="margin: 4px 0;"><strong>Kode Tiket:</strong> <span style="color: #6ee7b7;">{ticket_code}</span></p>
            <p style="margin: 4px 0;"><strong>Waktu:</strong> Sabtu, 28 November 2026 (10.00 – 11.30 WIB)</p>
            <p style="margin: 4px 0;"><strong>Lokasi:</strong> Menara 165, Hall Andalusia 3</p>
            <p style="margin: 4px 0;"><strong>Pemateri:</strong> Ustadzah Jasmine Al Zahrah</p>
        </div>

        <div style="text-align: center; margin: 24px 0; background: #ffffff; padding: 20px; border-radius: 12px;">
            <img src="cid:qrcode_image" alt="QR Code Ticket" style="width: 220px; height: 220px; display: block; margin: 0 auto;">
            <p style="font-family: monospace; color: #050a08; font-size: 14px; font-weight: bold; margin-top: 10px;">
                {ticket_code}
            </p>
        </div>

        <p style="font-family: Arial, sans-serif; font-size: 12px; color: #94a3b8; text-align: center;">
            Tunjukkan QR Code ini kepada panitia di meja registrasi saat memasuki lokasi acara.<br>
            Narahubung: Naila (08123456789)
        </p>
    </div>
    """

    msg.attach(MIMEText(html_content, "html"))

    # Lampirkan gambar QR Code (Inline & Attachment)
    qr_bytes = base64.b64decode(qr_base64)
    img_inline = MIMEImage(qr_bytes, _subtype="png")
    img_inline.add_header("Content-ID", "<qrcode_image>")
    img_inline.add_header("Content-Disposition", "inline",
                          filename=f"QR-{ticket_code}.png")
    msg.attach(img_inline)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)


def get_kuota_maksimal() -> int:
    if not supabase:
        return 320
    try:
        res = supabase.table("pengaturan").select(
            "kuota_maksimal").eq("id", 1).execute()
        if res.data:
            return res.data[0]["kuota_maksimal"]
    except Exception:
        pass
    return 320


# ==========================================
# PUBLIC ROUTES
# ==========================================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/daftar", methods=["GET", "POST"])
def daftar():
    if request.method == "POST":
        nama = request.form.get("nama", "").strip()
        email = request.form.get("email", "").strip()
        no_telp = request.form.get("no_telp", "").strip()
        umur = int(request.form.get("umur", 0))
        paket = request.form.get("paket", "Normal")
        total_bayar = 100000 if paket == "Special" else 30000
        file_bukti = request.files.get("bukti_tf")

        # 1. Generate Kode Tiket Unik & QR Code di sistem
        unique_suffix = uuid.uuid4().hex[:6].upper()
        ticket_code = f"TWR-{unique_suffix}"
        qr_base64 = generate_qr_base64(ticket_code)

        # 2. Upload Bukti Transfer ke Supabase Storage
        bukti_tf_url = ""
        if supabase and file_bukti and file_bukti.filename:
            ext = os.path.splitext(file_bukti.filename)[1].lower() or ".jpg"
            storage_filename = f"tf_{ticket_code}_{uuid.uuid4().hex[:4]}{ext}"
            file_bytes = file_bukti.read()
            content_type = file_bukti.mimetype or "image/jpeg"

            supabase.storage.from_(SUPABASE_BUCKET).upload(
                path=storage_filename,
                file=file_bytes,
                file_options={"content-type": content_type}
            )
            bukti_tf_url = supabase.storage.from_(
                SUPABASE_BUCKET).get_public_url(storage_filename)

        # 3. Simpan Data Peserta & QR ke Tabel Supabase
        if supabase:
            supabase.table("peserta").insert({
                "nama": nama,
                "email": email,
                "no_telp": no_telp,
                "umur": umur,
                "paket": paket,
                "total_bayar": total_bayar,
                "bukti_tf_url": bukti_tf_url,
                "qr_code": ticket_code,
                "qr_base64": qr_base64,
                "email_sent": False,
                "status_hadir": False,
                "waktu_scan": None
            }).execute()

        return redirect(url_for("sukses"))

    return render_template("daftar.html")


@app.route("/sukses")
def sukses():
    return render_template("sukses.html")


# ==========================================
# AUTH & ADMIN ROUTES
# ==========================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Password admin salah. Silakan coba kembali.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("index"))


@app.route("/admin")
@login_required
def admin_dashboard():
    peserta_list = []
    if supabase:
        res = supabase.table("peserta").select(
            "*").order("created_at", desc=True).execute()
        peserta_list = res.data or []

    total_terdaftar = len(peserta_list)
    sudah_hadir = sum(1 for p in peserta_list if p.get("status_hadir"))
    belum_hadir = total_terdaftar - sudah_hadir
    kuota_maksimal = get_kuota_maksimal()
    sisa_kuota = max(0, kuota_maksimal - total_terdaftar)

    return render_template(
        "admin.html",
        peserta_list=peserta_list,
        total_terdaftar=total_terdaftar,
        sudah_hadir=sudah_hadir,
        belum_hadir=belum_hadir,
        kuota_maksimal=kuota_maksimal,
        sisa_kuota=sisa_kuota
    )


@app.route("/admin/kuota", methods=["POST"])
@login_required
def update_kuota():
    kuota_baru = int(request.form.get("kuota", 320))
    if supabase:
        supabase.table("pengaturan").upsert(
            {"id": 1, "kuota_maksimal": kuota_baru}).execute()
        flash(
            f"Kuota pendaftaran berhasil diperbarui menjadi {kuota_baru}.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/send-qr/<int:peserta_id>", methods=["POST"])
@login_required
def admin_send_qr(peserta_id):
    if not supabase:
        return jsonify({"success": False, "message": "Supabase belum terhubung"}), 500

    res = supabase.table("peserta").select("*").eq("id", peserta_id).execute()
    if not res.data:
        return jsonify({"success": False, "message": "Data peserta tidak ditemukan"}), 404

    peserta = res.data[0]
    qr_b64 = peserta.get("qr_base64") or generate_qr_base64(peserta["qr_code"])

    try:
        send_ticket_email(
            recipient_email=peserta["email"],
            nama=peserta["nama"],
            paket=peserta["paket"],
            ticket_code=peserta["qr_code"],
            qr_base64=qr_b64
        )
        supabase.table("peserta").update(
            {"email_sent": True}).eq("id", peserta_id).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/admin/delete/<int:peserta_id>", methods=["POST"])
@login_required
def delete_peserta(peserta_id):
    if supabase:
        supabase.table("peserta").delete().eq("id", peserta_id).execute()
        flash("Data peserta berhasil dihapus.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/reset-hadir", methods=["POST"])
@login_required
def reset_hadir():
    if supabase:
        supabase.table("peserta").update(
            {"status_hadir": False, "waktu_scan": None}).neq("id", 0).execute()
        flash("Seluruh status kehadiran peserta telah di-reset.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete-all", methods=["POST"])
@login_required
def delete_all_peserta():
    if supabase:
        supabase.table("peserta").delete().neq("id", 0).execute()
        flash("Seluruh data peserta berhasil dihapus.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/export")
@login_required
def export_csv():
    peserta_list = []
    if supabase:
        res = supabase.table("peserta").select(
            "*").order("id", desc=False).execute()
        peserta_list = res.data or []

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "No", "Nama Lengkap", "Email", "No Telp", "Umur",
        "Paket", "Total Bayar", "Kode Tiket", "Email QR Terkirim",
        "Status Hadir", "Waktu Scan", "Link Bukti TF"
    ])

    for idx, p in enumerate(peserta_list, start=1):
        writer.writerow([
            idx,
            p.get("nama"),
            p.get("email"),
            p.get("no_telp"),
            p.get("umur"),
            p.get("paket"),
            p.get("total_bayar"),
            p.get("qr_code"),
            "Sudah" if p.get("email_sent") else "Belum",
            "Hadir" if p.get("status_hadir") else "Belum Hadir",
            p.get("waktu_scan") or "-",
            p.get("bukti_tf_url") or "-"
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment;filename=peserta_the_white_reflection.csv"}
    )


# ==========================================
# SCANNER ROUTES
# ==========================================
@app.route("/scan")
@login_required
def scan_page():
    return render_template("scan.html")


@app.route("/api/verify-qr", methods=["POST"])
@login_required
def verify_qr():
    if not supabase:
        return jsonify({"success": False, "message": "Database belum terhubung"}), 500

    data = request.get_json() or {}
    qr_code = data.get("qr_code", "").strip()

    if not qr_code:
        return jsonify({"success": False, "message": "Kode tiket kosong"}), 400

    res = supabase.table("peserta").select(
        "*").eq("qr_code", qr_code).execute()
    if not res.data:
        return jsonify({"success": False, "message": f"Tiket '{qr_code}' tidak terdaftar."}), 404

    peserta = res.data[0]
    if peserta.get("status_hadir"):
        return jsonify({
            "success": False,
            "message": f"Tiket atas nama {peserta['nama']} sudah pernah di-scan pada {peserta.get('waktu_scan')}."
        }), 400

    waktu_sekarang = get_wib_now()
    supabase.table("peserta").update({
        "status_hadir": True,
        "waktu_scan": waktu_sekarang
    }).eq("id", peserta["id"]).execute()

    return jsonify({
        "success": True,
        "nama": peserta["nama"],
        "paket": peserta["paket"],
        "waktu_scan": waktu_sekarang
    })


if __name__ == "__main__":
    app.run(debug=True)
