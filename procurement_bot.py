import streamlit as st
import pandas as pd
import re
from pathlib import Path
import plotly.express as px
import requests
import io

st.set_page_config(page_title="Procurement & Vendor Data Checker", layout="wide")
st.title("📋 Automation Bots")

# Sidebar
st.sidebar.title("Navigation")
section = st.sidebar.radio("Choose Section", ["📊 Summary Dashboard", "📁 Generated Reports"])

categories = {
    "Vendor Master Analysis": [
        "Vendors Missing Mandatory Fields",
        "Vendors with Duplicate PANs",
        "Vendor PAN Matches Employee PAN",
        "Invalid GSTINs",
        "Invalid PANs",
        "Duplicate Vendor Codes",
        "Vendors Missing Contact Details"
    ],
    "PO Analysis": [
        "Different Rates for Same Item+Vendor+Date",
        "Possible DoA Bypass",
        "Duplicate PO Numbers",
        "PO Date Earlier Than Entry Date",
        "POs Created on Sundays",
        "PO Created & Approved by Same User"
    ]
}

selected_category = st.sidebar.selectbox("Choose Report Category", list(categories.keys()))
selected_reports = categories[selected_category]

st.sidebar.markdown("---")
for report_name in selected_reports:
    anchor = report_name.replace(" ", "_")
    st.sidebar.markdown(f"""
        <a href="#{anchor}" style="text-decoration: none;">
            <button style="background-color:#000000;border:none;color:white;padding:8px 16px;text-align:center;text-decoration:none;display:inline-block;font-size:14px;margin:4px 2px;cursor:pointer;border-radius:12px;width:100%">{report_name}</button>
        </a>
    """, unsafe_allow_html=True)

st.header("Upload Required Files")
po_file = st.file_uploader("1️⃣ Upload PO Report (CSV or Excel)", type=["csv", "xls", "xlsx"], key="po_file")
vendor_file = st.file_uploader("2️⃣ Upload Vendor Master (CSV or Excel)", type=["csv", "xls", "xlsx"], key="vendor_file")
employee_file = st.file_uploader("3️⃣ Upload Employee Master (CSV or Excel)", type=["csv", "xls", "xlsx"], key="employee_file")

def load_file(file):
    try:
        suffix = Path(file.name).suffix.lower()
        if suffix == ".csv":
            df = pd.read_csv(file, encoding="ISO-8859-1")
        else:
            df = pd.read_excel(file)
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        st.error(f"Error loading {file.name}: {str(e)}")
        return None

report = {}

if po_file and vendor_file and employee_file:
    df_po = load_file(po_file)
    df_vendor = load_file(vendor_file)
    df_employee = load_file(employee_file)

    if df_po is not None and df_vendor is not None and df_employee is not None:
        if all(col in df_po.columns for col in ['Short Text', 'Document Date', 'Supplier/Supplying Plant', 'Net Price']):
            g1 = df_po.groupby(['Short Text', 'Document Date', 'Supplier/Supplying Plant'])
            price_diff = g1['Net Price'].nunique().reset_index()
            price_diff = price_diff[price_diff['Net Price'] > 1]
            report['Different Rates for Same Item+Vendor+Date'] = price_diff

        if all(col in df_po.columns for col in ['Short Text', 'Document Date', 'Supplier/Supplying Plant']):
            g2 = df_po.groupby(['Short Text', 'Document Date', 'Supplier/Supplying Plant'])
            doa_bypass = g2.size().reset_index(name='Count')
            doa_bypass = doa_bypass[doa_bypass['Count'] > 1]
            report['Possible DoA Bypass'] = doa_bypass

        if 'Purchasing Document' in df_po.columns:
            report['Duplicate PO Numbers'] = df_po[df_po.duplicated('Purchasing Document', keep=False)]

        if 'PR Number' in df_po.columns:
            report['Duplicate PR Numbers'] = df_po[df_po.duplicated('PR Number', keep=False)]

        if all(col in df_po.columns for col in ['PO Creator', 'PO Approver']):
            report['Same PO Creator and Approver'] = df_po[df_po['PO Creator'] == df_po['PO Approver']]

        if all(col in df_po.columns for col in ['Document Date', 'Entry Date']):
            df_po['Document Date'] = pd.to_datetime(df_po['Document Date'], errors='coerce')
            df_po['Entry Date'] = pd.to_datetime(df_po['Entry Date'], errors='coerce')
            report['PO Date Earlier Than Entry Date'] = df_po[df_po['Document Date'] < df_po['Entry Date']]

        if 'Creation Date' in df_po.columns:
            df_po['Creation Date'] = pd.to_datetime(df_po['Creation Date'], errors='coerce')
            report['POs Created on Sundays'] = df_po[df_po['Creation Date'].dt.dayofweek == 6]

        for creator_col in ['Created by', 'PO Creator']:
            for approver_col in ['Approved by', 'PO Approver']:
                if creator_col in df_po.columns and approver_col in df_po.columns:
                    report['PO Created & Approved by Same User'] = df_po[df_po[creator_col] == df_po[approver_col]]
                    break

        required = ['BANK NAME', 'BANK ACC NO.', 'IFSC CODE', 'PAN NO', 'AADHAAR NO']
        if all(col in df_vendor.columns for col in required):
            report['Vendors Missing Mandatory Fields'] = df_vendor[df_vendor[required].isnull().any(axis=1) | (df_vendor[required] == '').any(axis=1)]

        if 'PAN NO' in df_vendor.columns:
            report['Vendors with Duplicate PANs'] = df_vendor[df_vendor.duplicated('PAN NO', keep=False) & df_vendor['PAN NO'].notna() & (df_vendor['PAN NO'] != '')]

        if 'PAN NO' in df_vendor.columns and 'PAN No.' in df_employee.columns:
            vendor_pan = df_vendor['PAN NO'].astype(str).str.strip().str.upper()
            emp_pan = df_employee['PAN No.'].astype(str).str.strip().str.upper()
            common_pan = vendor_pan[vendor_pan.isin(emp_pan)]
            report['Vendor PAN Matches Employee PAN'] = df_vendor[df_vendor['PAN NO'].isin(common_pan)]

        if 'GSTIN' in df_vendor.columns:
            gstin = df_vendor['GSTIN'].astype(str).str.strip().str.upper()
            pattern = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$'
            report['Invalid GSTINs'] = df_vendor[gstin.notna() & ~gstin.str.match(pattern)]

        if 'PAN NO' in df_vendor.columns:
            pan = df_vendor['PAN NO'].astype(str).str.strip().str.upper()
            pattern = r'^[A-Z]{5}[0-9]{4}[A-Z]$'
            report['Invalid PANs'] = df_vendor[pan.notna() & ~pan.str.match(pattern)]

        if 'VENDOR CODE' in df_vendor.columns:
            report['Duplicate Vendor Codes'] = df_vendor[df_vendor.duplicated('VENDOR CODE', keep=False)]

        if {'EMAIL ID', 'MOBILE NO.'}.issubset(df_vendor.columns):
            contact_missing = df_vendor[(df_vendor['EMAIL ID'].astype(str).str.strip() == '') | (df_vendor['MOBILE NO.'].astype(str).str.strip() == '')]
            report['Vendors Missing Contact Details'] = contact_missing

        filtered_reports = {k: v for k, v in report.items() if k in selected_reports}

        if section == "📊 Summary Dashboard":
            st.subheader(f"Summary of {selected_category}")
            summary_df = pd.DataFrame({"Check": list(filtered_reports.keys()), "Issues Found": [len(df) for df in filtered_reports.values()]})
            st.dataframe(summary_df)
            st.plotly_chart(px.bar(summary_df, x="Check", y="Issues Found", text_auto=True), use_container_width=True)

        elif section == "📁 Generated Reports":
            for i, (title, df) in enumerate(filtered_reports.items()):
                anchor = title.replace(" ", "_")
                st.markdown(f'<a name="{anchor}"></a>', unsafe_allow_html=True)
                st.subheader(title)
                st.write(f"Records found: {len(df)}")
                st.dataframe(df)

                col1, col2 = st.columns([1, 1])

                with col1:
                    st.download_button(f"Download {title}", df.to_csv(index=False), file_name=f"{title}.csv", key=f"download_{i}")

                with col2:
                    if st.button(f"Push Observation - {title}", key=f"push_{i}"):
                        try:
                            excel_buffer = io.BytesIO()
                            df.to_excel(excel_buffer, index=False, engine='openpyxl')
                            excel_buffer.seek(0)

                            payload = {
                                'audit_type': 'general',
                                'due_date': '2025-06-18',
                                'created_by': 'Super Admin',
                                'organization_name': 'Capitall Consultancy Services Ltd',
                                'company': 'Capitall Consultancy Services Limited',
                                'locations': 'Delhi',
                                'financial_year': '2024-25',
                                'quarter': 'Q3',
                                'observation_heading': title,
                                'observation_description': title,
                                'issue_type': title,
                                'reviewer_responsible': 'Atishay Jain'
                            }

                            files = [
                                ('attachments[]', (f"{title}.xlsx", excel_buffer, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'))
                            ]

                            headers = {
                                'x-api-key': '47fca1d2b8e14eab9d6c463a8fbe5c23'
                            }

                            response = requests.post("https://kkc.grc.capitall.io/api/observation/create", data=payload, files=files, headers=headers)

                            if response.status_code == 200:
                                st.success(f"✅ Observation for '{title}' pushed successfully.")
                            else:
                                st.error(f"❌ Failed to push observation. {response.status_code} - {response.text}")

                        except Exception as e:
                            st.error(f"Exception occurred: {str(e)}")
else:
    st.warning("Please upload all required files.")
