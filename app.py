from flask import Flask, render_template, request, send_file
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image
import os

app = Flask(__name__)
UPLOAD_FOLDER = 'static_pdfs'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

class PDF(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.cell(0, 10, f'Page {self.page_no()}', align="C")

def generate_pdf(data, header_img, sig_img):
    pdf = PDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    
    # --- 1. CONFIGURATION ---
    base_font_size = int(data.get('font_size', 10))
    
    # --- 2. HEADER (SMART HEIGHT) ---
    current_y = 20
    if header_img:
        try:
            pdf.image(header_img, x=10, y=10, w=277)
            with Image.open(header_img) as img:
                w, h = img.size
                aspect_ratio = h / w
                rendered_height = 277 * aspect_ratio
            current_y = 10 + rendered_height + 10
            pdf.set_y(current_y)
        except Exception:
            pdf.set_y(60)
            current_y = 60
    else:
        pdf.set_y(20)

    # --- 3. TO ADDRESS ---
    raw_addr = data.get('client_address', '').strip()
    if raw_addr:
        if raw_addr.upper().startswith("TO,"): raw_addr = raw_addr[3:].strip()
        elif raw_addr.upper().startswith("TO"): raw_addr = raw_addr[2:].strip()
        raw_addr = raw_addr.lstrip(";:,. ")

        pdf.set_font("helvetica", "B", base_font_size)
        pdf.cell(100, 5, "TO,", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("helvetica", size=base_font_size)
        for line in raw_addr.split('\n'):
            pdf.cell(100, 5, line.strip(), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # --- 4. DATE & BILL NO ---
    pdf.set_y(current_y)
    pdf.set_font("helvetica", "B", base_font_size)
    
    if data.get('date'):
        pdf.set_x(200)
        pdf.cell(80, 5, f"DATE: {data['date']}", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    
    if data.get('bill_no') and data.get('bill_no').strip() != "":
        pdf.set_x(200)
        pdf.cell(80, 5, f"BILL NO: {data['bill_no']}", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_y(max(pdf.get_y(), current_y + 20) + 10)

    # --- 5. SUBJECT LINE ---
    raw_subject = data.get('subject', '').strip()
    if raw_subject:
        if raw_subject.upper().startswith("SUB:"): raw_subject = raw_subject[4:].strip()
        elif raw_subject.upper().startswith("SUB"): raw_subject = raw_subject[3:].strip()
        raw_subject = raw_subject.lstrip(";:,. ")

        pdf.set_font("helvetica", "B", base_font_size)
        pdf.cell(15, 8, "SUB:", align='L')
        pdf.set_font("helvetica", size=base_font_size)
        pdf.multi_cell(0, 8, raw_subject, align='L')
        pdf.ln(1)

    # --- 6. PERIOD (FROM DATE - TO DATE) ---
    # This is the NEW section you asked for
    if data.get('from_date') and data.get('to_date'):
        period_text = f"PERIOD FROM {data['from_date']} TO {data['to_date']}"
        pdf.set_font("helvetica", "B", base_font_size)
        pdf.cell(0, 6, period_text, align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)

    pdf.ln(2)

    # --- 7. SMART COLUMNS ---
    columns = data.getlist('col_header')
    if columns:
        row_types = data.getlist('row_type')
        all_cells = data.getlist('cell_value')
        col_weights = [len(col) + 4 for col in columns] 
        current_idx = 0
        for r_type in row_types:
            if r_type == 'data':
                for i in range(len(columns)):
                    if current_idx < len(all_cells):
                        cell_text = str(all_cells[current_idx])
                        if len(cell_text) > col_weights[i]: col_weights[i] = len(cell_text)
                    current_idx += 1
            elif r_type in ['note', 'total']:
                if r_type == 'note': current_idx += 1
                if r_type == 'total': current_idx += 1
        total_weight = sum(col_weights)
        page_width = 277 
        final_col_widths = [(w / total_weight) * page_width for w in col_weights]

        # --- 8. DRAW TABLE ---
        pdf.set_font("helvetica", "B", base_font_size)
        pdf.set_fill_color(230, 230, 230)
        for i, col in enumerate(columns):
            pdf.cell(final_col_widths[i], 8, col, border=1, fill=True, align='C')
        pdf.ln()

        pdf.set_font("helvetica", size=base_font_size)
        current_idx = 0 
        for r_type in row_types:
            if r_type == 'data':
                row_height = 8
                for i in range(len(columns)):
                    if current_idx < len(all_cells): val = str(all_cells[current_idx])
                    else: val = ""
                    width = final_col_widths[i]
                    available_width = width - 2 
                    current_font_size = base_font_size
                    pdf.set_font("helvetica", size=current_font_size)
                    while pdf.get_string_width(val) > available_width and current_font_size > 5:
                        current_font_size -= 0.5
                        pdf.set_font("helvetica", size=current_font_size)
                    if pdf.get_string_width(val) > available_width:
                         while pdf.get_string_width(val + "...") > available_width and len(val) > 0:
                             val = val[:-1]
                         val += "..."
                    pdf.cell(width, row_height, val, border=1, align='C')
                    pdf.set_font("helvetica", size=base_font_size)
                    current_idx += 1
                pdf.ln()
            elif r_type == 'note':
                if current_idx < len(all_cells): note_text = all_cells[current_idx]
                else: note_text = ""
                pdf.set_font("helvetica", "I", base_font_size) 
                pdf.cell(page_width, 8, str(note_text), border=1, align='L') 
                current_idx += 1
                pdf.ln()
            elif r_type == 'total':
                if current_idx < len(all_cells): total_val = all_cells[current_idx]
                else: total_val = ""
                pdf.set_font("helvetica", "B", base_font_size)
                width_label = sum(final_col_widths[:-1])
                width_value = final_col_widths[-1]
                pdf.cell(width_label, 8, "TOTAL / GRAND TOTAL ", border=1, align='R')
                pdf.cell(width_value, 8, str(total_val), border=1, align='R')
                current_idx += 1
                pdf.ln()

    # --- 9. SIGNATURE ---
    if data.get('signer_name') or sig_img:
        if pdf.get_y() > 150: pdf.add_page()
        pdf.ln(10)
        pdf.set_x(200)
        pdf.set_font("helvetica", "B", base_font_size)
        if data.get('company_name'):
             pdf.cell(60, 5, f"For {data['company_name']}", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if sig_img:
            pdf.image(sig_img, x=215, y=pdf.get_y() + 2, w=30)
            pdf.ln(15)
        else:
            pdf.ln(15)
        pdf.set_x(200)
        pdf.cell(60, 5, f"({data.get('signer_name', '')})", align='C')

    output_path = os.path.join(UPLOAD_FOLDER, 'bill.pdf')
    pdf.output(output_path)
    return output_path

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        h_file = request.files.get('header_img')
        s_file = request.files.get('sig_img')
        h_path = None
        s_path = None
        if h_file and h_file.filename:
            h_path = os.path.join(UPLOAD_FOLDER, "temp_header.jpg")
            h_file.save(h_path)
        if s_file and s_file.filename:
            s_path = os.path.join(UPLOAD_FOLDER, "temp_sig.png")
            s_file.save(s_path)
        try:
            pdf_path = generate_pdf(request.form, h_path, s_path)
            return send_file(pdf_path, as_attachment=True)
        except Exception as e:
            return f"Error: {str(e)}"
    return render_template('bill.html')

if __name__ == '__main__':
    app.run(debug=True)
