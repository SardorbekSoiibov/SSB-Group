"""Safe spreadsheet and Unicode PDF exports from the same backend report rows."""
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from django.http import HttpResponse

def export_report(kind,name,headers,rows,title):
    if kind=='xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        book=Workbook();sheet=book.active;sheet.title='SSB Boshqaruv'
        sheet.append(headers)
        for cell in sheet[1]:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='252A33');cell.alignment=Alignment(vertical='center')
        sheet.row_dimensions[1].height=28
        for row in rows:
            clean=[]
            for value in row:
                if value is None:clean.append('')
                elif isinstance(value,(Decimal,int)):
                    # Excel preserves only 15 significant numeric digits.
                    exact=Decimal(value)
                    clean.append(str(value) if len(exact.normalize().as_tuple().digits)>15 else value)
                elif isinstance(value,float):clean.append(value)
                else:
                    text=str(value)
                    clean.append("'"+text if text.lstrip().startswith(('=','+','-','@')) else text)
            sheet.append(clean)
        sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
        for column in sheet.columns:
            width=min(55,max(14,max(len(str(cell.value or '')) for cell in column)+2));sheet.column_dimensions[column[0].column_letter].width=width
        buffer=BytesIO();book.save(buffer)
        response=HttpResponse(buffer.getvalue(),content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    elif kind=='pdf':
        from reportlab.platypus import SimpleDocTemplate,Table,TableStyle,Paragraph,Spacer
        from reportlab.lib.pagesizes import A4,landscape
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        font='Helvetica'
        for candidate in [Path('C:/Windows/Fonts/segoeui.ttf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]:
            if candidate.is_file():
                if 'SSBReport' not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont('SSBReport',str(candidate)))
                font='SSBReport';break
        styles=getSampleStyleSheet();style=styles['BodyText'];style.fontName=font;style.fontSize=8;style.leading=12
        buffer=BytesIO();document=SimpleDocTemplate(buffer,pagesize=landscape(A4),rightMargin=28,leftMargin=28,topMargin=30,bottomMargin=30)
        data=[[Paragraph(escape(str(cell)),style) for cell in headers]]
        data += [[Paragraph(escape(str(cell if cell is not None else '')),style) for cell in row] for row in rows]
        if len(data)==1:data.append([Paragraph('Ma’lumot yo‘q',style)]+['']*(len(headers)-1))
        table=Table(data,repeatRows=1,colWidths=[(landscape(A4)[0]-56)/max(1,len(headers))]*len(headers))
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#EDF0F4')),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#E2E6EC')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
        document.build([Paragraph(escape(title),style),Spacer(1,18),table])
        response=HttpResponse(buffer.getvalue(),content_type='application/pdf')
    else:raise ValueError('Unsupported export format')
    response['Content-Disposition']=f'attachment; filename="{name}.{kind}"';response['Cache-Control']='private, no-store'
    return response
