from flask import Flask, render_template, request, send_file, jsonify
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image
import os
import sqlite3

app = Flask(__name__)
# Use /tmp for Render Cloud compatibility
UPLOAD_FOLDER = '/tmp/static_pdfs'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
DB_FILE = '/tmp/billcraft_v15.db'

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS bills (bill_no TEXT UNIQUE)')
    c.execute('CREATE TABLE IF NOT EXISTS trucks (truck_no TEXT UNIQUE)')
    conn.commit()
    conn.close()

init_db()

class PDF(FPDF):
    def footer(self):
        # Position at 1.5 cm from bottom
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.cell(0, 10, f'Page {self.page_no()}', align="C")

def generate_pdf(data, header_img, sig_img, custom_filename):
    # A4 Landscape is 297mm width x 210mm height
    pdf = PDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    
    base_font_size = int(data.get('font_size', 10))
    
    # --- 1. HEADER (Compact Mode) ---
    current_y = 15
    if header_img:
        try:
            # Draw Image
            pdf.image(header_img, x=10, y=10, w=277)
            # Calculate Height
            with Image.open(header_img) as img:
                w, h = img.size
                rendered_height = 277 * (h / w)
            # Set Y just below image
            current_y = 10 + rendered_height + 2
            pdf.set_y(current_y)
        except:
            pdf.set_y(50)
            current_y = 50
    else:
        pdf.set_y(15)

    # --- 2. ADDRESS (Left Side) ---
    raw_addr = data.get('client_address', '').strip()
    if raw_addr:
        # Clean up
        if raw_addr.upper().startswith("TO,"): raw_addr = raw_addr[3:].strip()
        elif raw_addr.upper().startswith("TO"): raw_addr = raw_addr[2:].strip()
        # Limit to 10 lines
        addr_lines = raw_addr.split('\n')[:10]
        
        pdf.set_font("helvetica", "B", base_font_size)
        pdf.cell(100, 5, "TO,", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("helvetica", size=base_font_size)
        for line in addr_lines:
            pdf.cell(100, 5, line.strip(), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # --- 3. DATE & BILL NO (Right Side) ---
    # We move cursor back up to where Address started
    pdf.set_y(current_y) 
    pdf.set_font("helvetica", "B", base_font_size)
    
    # Date
    pdf.set_x(200)
    pdf.cell(80, 5, f"DATE: {data['date']}", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    # Bill No
    pdf.set_x(200)
    pdf.cell(80, 5, f"BILL NO: {data['bill_no']}", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Ensure we are below the lowest element (Address OR Bill Info)
    address_height = (len(raw_addr.split('\n')) * 5) + 10
    pdf.set_y(max(pdf.get_y(), current_y + address_height) + 2)

    # --- 4. CENTERED SUBJECT & PERIOD ---
    
    # SUBJECT (Centered)
    raw_subject = data.get('subject', '').strip()
    if raw_subject:
        if raw_subject.upper().startswith("SUB:"): raw_subject = raw_subject[4:].strip()
        elif raw_subject.upper().startswith("SUB"): raw_subject = raw_subject[3:].strip()
        
        pdf.set_font("helvetica", "B", base_font_size)
        # align='C' centers the text
        pdf.multi_cell(0, 6, f"SUB: {raw_subject}", align='C')
        pdf.ln(1)

    # PERIOD (Centered)
    if data.get('from_date') and data.get('to_date'):
        period_text = f"PERIOD FROM {data['from_date']} TO {data['to_date']}"
        pdf.set_font("helvetica", "B", base_font_size)
        pdf.cell(0, 6, period_text, align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1)
    
    pdf.ln(2) # Small gap before table

    # --- 5. COMPACT TABLE ---
    columns = data.getlist('col_header')
    if columns:
        row_types = data.getlist('row_type')
        all_cells = data.getlist('cell_value')
        col_weights = [len(col) + 4 for col in columns] 
        current_idx = 0
        
        # Calculate widths
        for r_type in row_types:
            if r_type == 'data':
                for i in range(len(columns)):
                    if current_idx < len(all_cells):
                        cell_text = str(all_cells[current_idx])
                        if len(cell_text) > col_weights[i]: col_weights[i] = len(cell_text)
                    current_idx += 1
            elif r_type in ['note', 'total']:
                current_idx += 1
        
        total_weight = sum(col_weights)
        page_width = 277 
        final_col_widths = [(w / total_weight) * page_width for w in col_weights]

        # Header Row
        pdf.set_font("helvetica", "B", base_font_size)
        pdf.set_fill_color(230, 230, 230)
        row_height = 7 # Slightly smaller row height to fit more
        
        for i, col in enumerate(columns):
            pdf.cell(final_col_widths[i], row_height, col, border=1, fill=True, align='C')
        pdf.ln()

        # Data Rows
        pdf.set_font("helvetica", size=base_font_size)
        current_idx = 0 
        for r_type in row_types:
            if r_type == 'data':
                for i in range(len(columns)):
                    val = str(all_cells[current_idx]) if current_idx < len(all_cells) else ""
                    width = final_col_widths[i]
                    
                    # Auto-Shrink Font to fit in cell
                    available_width = width - 2 
                    temp_font_size = base_font_size
                    pdf.set_font("helvetica", size=temp_font_size)
                    while pdf.get_string_width(val) > available_width and temp_font_size > 6:
                        temp_font_size -= 0.5
                        pdf.set_font("helvetica", size=temp_font_size)
                    
                    pdf.cell(width, row_height, val, border=1, align='C')
                    pdf.set_font("helvetica", size=base_font_size)
                    current_idx += 1
                pdf.ln()
                
            elif r_type == 'note':
                note_text = str(all_cells[current_idx]) if current_idx < len(all_cells) else ""
                pdf.set_font("helvetica", "I", base_font_size) 
                pdf.cell(page_width, row_height, note_text, border=1, align='L') 
                current_idx += 1
                pdf.ln()
                
            elif r_type == 'total':
                total_val = str(all_cells[current_idx]) if current_idx < len(all_cells) else ""
                pdf.set_font("helvetica", "B", base_font_size)
                width_label = sum(final_col_widths[:-1])
                width_value = final_col_widths[-1]
                pdf.cell(width_label, row_height, "TOTAL / GRAND TOTAL ", border=1, align='R')
                pdf.cell(width_value, row_height, total_val, border=1, align='R')
                current_idx += 1
                pdf.ln()

    # --- 6. SIGNATURE (Smart Placement) ---
    if data.get('signer_name') or sig_img:
        # Only add new page if we are DANGEROUSLY close to bottom (190mm)
        # Previous limit was 150mm, which was forcing page 2 too early.
        if pdf.get_y() > 190: 
            pdf.add_page()
        
        pdf.ln(5)
        pdf.set_x(200)
        pdf.set_font("helvetica", "B", base_font_size)
        
        company = data.get('company_name', '')
        if company:
            # Fix "For For" issue
            prefix = "For " if not company.lower().startswith("for") else ""
            pdf.cell(60, 5, f"{prefix}{company}", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
        if sig_img:
            pdf.image(sig_img, x=215, y=pdf.get_y() + 2, w=30)
            pdf.ln(15)
        else:
            pdf.ln(15)
            
        pdf.set_x(200)
        pdf.cell(60, 5, f"({data.get('signer_name', '')})", align='C')

    # Filename Handling
    safe_name = "".join([c for c in custom_filename if c.isalpha() or c.isdigit() or c in " ._-"])
    if not safe_name: safe_name = "bill"
    if not safe_name.lower().endswith(".pdf"): safe_name += ".pdf"
    output_path = os.path.join(UPLOAD_FOLDER, safe_name)
    pdf.output(output_path)
    return output_path

@app.route('/api/trucks')
def get_trucks():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT truck_no FROM trucks")
    trucks = [row[0] for row in c.fetchall()]
    conn.close()
    return jsonify(trucks)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        user_date = request.form.get('date', '').strip()
        bill_no = request.form.get('bill_no', '').strip().upper()
        address = request.form.get('client_address', '').strip()

        # Strict validation
        if not user_date: return "ERROR: Date is missing."
        if not bill_no: return "ERROR: Bill Number is missing."
        if not address: return "ERROR: Address is missing."

        # Database Ops
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Check Duplicate
        c.execute('SELECT * FROM bills WHERE bill_no = ?', (bill_no,))
        if c.fetchone():
            conn.close()
            return f"<h1>ERROR: Bill Number '{bill_no}' already exists!</h1>"
        
        c.execute('INSERT INTO bills (bill_no) VALUES (?)', (bill_no,))
        
        # Learn Trucks
        columns = request.form.getlist('col_header')
        row_types = request.form.getlist('row_type')
        all_cells = request.form.getlist('cell_value')
        
        truck_col_indices = []
        for i, col in enumerate(columns):
            name = col.upper()
            if any(k in name for k in ["TRUCK", "VEHICLE", "NO", "LORRY", "AUTO"]):
                truck_col_indices.append(i)
        
        current_idx = 0
        for r_type in row_types:
            if r_type == 'data':
                for i in range(len(columns)):
                    val = str(all_cells[current_idx]).strip().upper()
                    if i in truck_col_indices and val and len(val) > 4:
                         c.execute('INSERT OR IGNORE INTO trucks (truck_no) VALUES (?)', (val,))
                    current_idx += 1
            elif r_type in ['note', 'total']:
                current_idx += 1
        
        conn.commit()
        conn.close()

        # Files
        h_file = request.files.get('header_img')
        s_file = request.files.get('sig_img')
        user_filename = request.form.get('filename', 'bill').strip()
        
        h_path = None
        s_path = None
        if h_file and h_file.filename:
            h_path = os.path.join(UPLOAD_FOLDER, "temp_header.jpg")
            h_file.save(h_path)
        if s_file and s_file.filename:
            s_path = os.path.join(UPLOAD_FOLDER, "temp_sig.png")
            s_file.save(s_path)
            
        try:
            pdf_path = generate_pdf(request.form, h_path, s_path, user_filename)
            return send_file(pdf_path, as_attachment=True, download_name=os.path.basename(pdf_path))
        except Exception as e:
            return f"Error: {str(e)}"
            
    return render_template('bill.html')

if __name__ == '__main__':
    app.run(debug=True)
