"""
Static seed data for the catalogue module. Kept separate from seed.py (the idempotent
loader) so the data itself is easy to review/extend without touching loader logic.
"""

# ---------------------------------------------------------------------------
# Locations — the regions an AssignmentGroup can be bound to / a user's home_location.
# "HO" (Head Office) plus every region named in SPEC §2's assignment-group seed list.
# ---------------------------------------------------------------------------
LOCATIONS = [
    # code,        name,                 country,        timezone
    ("HO",         "Head Office",        "India",        "Asia/Kolkata"),
    ("VASIND",     "Vasind",             "India",        "Asia/Kolkata"),
    ("POLAND",     "Poland",             "Poland",       "Europe/Warsaw"),
    ("EGYPT",      "Egypt",              "Egypt",        "Africa/Cairo"),
    ("MEXICO",     "Mexico",             "Mexico",       "America/Mexico_City"),
    ("CHINA",      "China",              "China",        "Asia/Shanghai"),
    ("GERMANY",    "Germany",            "Germany",      "Europe/Berlin"),
    ("PHILIPPINES", "Philippines",       "Philippines",  "Asia/Manila"),
    ("COLUMBIA",   "Columbia",           "Colombia",     "America/Bogota"),
]

# ---------------------------------------------------------------------------
# Assignment Groups (SPEC §2) — 18 total: 9 regional "IT Infra - <region>" groups
# (location-bound) + 9 global specialist-domain groups (location-independent).
# ---------------------------------------------------------------------------
_REGIONAL_CODES = ["POLAND", "EGYPT", "MEXICO", "CHINA", "GERMANY", "PHILIPPINES", "COLUMBIA", "VASIND", "HO"]

ASSIGNMENT_GROUPS_REGIONAL = [f"IT Infra - {name}" for name in
                              ["Poland", "Egypt", "Mexico", "China", "Germany", "Philippines",
                               "Columbia", "Vasind", "HO"]]

ASSIGNMENT_GROUPS_GLOBAL = [
    "Network", "Wintel", "Storage", "Backup", "Unix - Linux", "Tools Support",
    "O365", "SCCM", "Digital Desk Support",
]

# ---------------------------------------------------------------------------
# IT Service Catalogue — 3-level hierarchy: Tower (category) -> Service (subcategory) ->
# Item. Each tower lists a representative 15-25 services per SPEC §1; each service is
# seeded with a small starter set of items rather than an exhaustive list (full breadth is
# expected to grow via the admin catalogue.edit permission in a later session — see
# /PROGRESS.md and the CatalogueItem docstring).
# ---------------------------------------------------------------------------
CATALOGUE = {
    "DATA_CENTER": {
        "name": "Data Center Services",
        "subcategories": {
            "SERVER_PROVISIONING": ("Server Provisioning", ["New VM Request", "Physical Server Request", "Decommission Request"]),
            "SERVER_PATCHING": ("Server Patching", ["OS Patch Deployment", "Emergency Patch"]),
            "SERVER_INCIDENT": ("Server Down/Degraded", ["Server Unresponsive", "High CPU/Memory Alert", "Disk Space Critical"]),
            "DC_ACCESS": ("Data Center Physical Access", ["Access Card Request", "Escort Visit Request"]),
            "VIRTUALIZATION": ("Virtualization Platform", ["Hypervisor Issue", "vCenter/Cluster Alert"]),
            "DC_POWER_COOLING": ("Power & Cooling", ["UPS Alert", "Cooling System Fault"]),
            "DC_NETWORKING": ("Data Center Networking", ["Rack Switch Port Request", "Cabling Request"]),
            "DC_CAPACITY": ("Capacity Planning", ["Storage/Compute Forecast Request"]),
            "DC_DR": ("DR / Business Continuity", ["DR Test Support", "Failover Request"]),
            "DC_DECOMM": ("Asset Decommission", ["Hardware Disposal Request"]),
            "DC_MONITORING": ("Server Monitoring Setup", ["New Monitoring Agent Install"]),
            "DC_MAINTENANCE": ("Scheduled Maintenance", ["Maintenance Window Request"]),
            "DC_OS_UPGRADE": ("OS Upgrade", ["In-place OS Upgrade Request"]),
            "DC_DB_HOSTING": ("Database Hosting Support", ["DB Server Provisioning"]),
            "DC_CERT": ("Certificate Management", ["Server Certificate Renewal"]),
            "DC_CAPACITY_ALERT": ("Capacity Alert", ["Disk/Volume Near Full Alert"]),
        },
    },
    "NETWORK": {
        "name": "Network",
        "subcategories": {
            "LAN_ISSUE": ("LAN Connectivity", ["No Network Access", "Intermittent Drops"]),
            "WAN_ISSUE": ("WAN / Site Link", ["Site Link Down", "Latency/Packet Loss"]),
            "WIFI_ISSUE": ("Wi-Fi", ["Cannot Connect to Wi-Fi", "Weak Signal Area"]),
            "VPN_ISSUE": ("VPN", ["VPN Connection Failure", "VPN Slow/Disconnecting"]),
            "FIREWALL": ("Firewall", ["Firewall Rule Request", "Port Open Request"]),
            "SWITCH_ROUTER": ("Switch/Router", ["Switch Port Down", "Router Configuration Change"]),
            "IP_ADDRESSING": ("IP Addressing / DHCP", ["New IP/Subnet Request", "DHCP Lease Issue"]),
            "DNS": ("DNS", ["DNS Record Request", "DNS Resolution Failure"]),
            "LOAD_BALANCER": ("Load Balancer", ["LB Configuration Change", "LB Health Check Failure"]),
            "NETWORK_MONITORING": ("Network Monitoring", ["New Device Monitoring Request"]),
            "BANDWIDTH": ("Bandwidth Management", ["Bandwidth Upgrade Request"]),
            "NAC": ("Network Access Control", ["Device Onboarding to NAC"]),
            "PROXY": ("Proxy / Internet Access", ["Site Blocked Unblock Request"]),
            "NETWORK_CHANGE": ("Network Change Request", ["Planned Network Change"]),
            "CCTV_NETWORK": ("CCTV/IoT Network Segment", ["CCTV Connectivity Issue"]),
        },
    },
    "CYBER_SECURITY": {
        "name": "Cyber Security",
        "subcategories": {
            "PHISHING": ("Phishing / Suspicious Email", ["Report Phishing Email", "Suspected Compromise"]),
            "MALWARE": ("Malware / Virus", ["Malware Detected Alert", "Antivirus Definition Issue"]),
            "ACCESS_REQUEST": ("Access Request", ["New Application Access", "Access Revocation"]),
            "PASSWORD_RESET": ("Password / Account", ["Password Reset", "Account Lockout"]),
            "MFA": ("Multi-Factor Authentication", ["MFA Enrollment Issue", "MFA Device Lost"]),
            "DLP": ("Data Loss Prevention", ["DLP Policy Alert", "DLP Exception Request"]),
            "VULN_MGMT": ("Vulnerability Management", ["Vulnerability Scan Finding", "Patch Exception Request"]),
            "SIEM_ALERT": ("SIEM / SOC Alert", ["SOC Escalation", "Suspicious Login Alert"]),
            "ENDPOINT_SECURITY": ("Endpoint Security", ["EDR Agent Issue", "Endpoint Isolation Request"]),
            "SECURITY_AUDIT": ("Security Audit / Compliance", ["Audit Evidence Request", "Compliance Questionnaire"]),
            "DATA_PRIVACY": ("Data Privacy (DPDP)", ["DSAR Request", "Data Breach Report"]),
            "THIRD_PARTY_RISK": ("Third-Party / Vendor Risk", ["Vendor Security Assessment"]),
            "CERT_MGMT": ("Certificate / PKI", ["SSL Certificate Request"]),
            "SECURITY_TRAINING": ("Security Awareness", ["Training Assignment Issue"]),
            "INCIDENT_RESPONSE": ("Security Incident Response", ["Declare Security Incident"]),
        },
    },
    "HELPDESK_FMS": {
        "name": "Helpdesk/FMS",
        "subcategories": {
            "GENERAL_QUERY": ("General IT Query", ["How-To Question", "General Assistance"]),
            "DESK_SIDE_SUPPORT": ("Desk-Side Support", ["On-Site Visit Request"]),
            "MEETING_ROOM_AV": ("Meeting Room / AV", ["Projector/Display Issue", "Conference Room Booking Support"]),
            "PRINTER_SUPPORT": ("Printer / Scanner", ["Printer Not Working", "Toner Replacement"]),
            "NEW_JOINER": ("New Joiner Setup", ["New Joiner IT Kit Request"]),
            "EXIT_OFFBOARDING": ("Exit / Offboarding", ["Employee Exit IT Checklist"]),
            "ASSET_MOVE": ("Asset Move/Add/Change", ["Desk Relocation Request"]),
            "FMS_TICKET_ROUTING": ("FMS Queue Routing", ["Vendor Desk Escalation"]),
            "STATIONERY_IT": ("IT Consumables", ["Cable/Adapter Request"]),
            "VC_SUPPORT": ("Video Conferencing Support", ["VC Call Drop Issue"]),
            "BADGE_ACCESS": ("Badge / Physical Access", ["Access Card Issue"]),
            "FLOOR_WALK": ("Floor Walk Support", ["Scheduled Floor Support Visit"]),
            "TRAINING_ROOM": ("Training Room Setup", ["Training Room IT Setup"]),
            "GENERIC_REQUEST": ("Other / Uncategorized", ["Miscellaneous Request"]),
        },
    },
    "EMAIL": {
        "name": "Email",
        "subcategories": {
            "MAILBOX_ISSUE": ("Mailbox Issue", ["Cannot Send/Receive Mail", "Mailbox Full"]),
            "DISTRIBUTION_LIST": ("Distribution List", ["New DL Request", "DL Membership Change"]),
            "SHARED_MAILBOX": ("Shared Mailbox", ["New Shared Mailbox Request", "Shared Mailbox Access"]),
            "EMAIL_SPAM": ("Spam / Junk Mail", ["Spam Filter Tuning", "Legit Mail Marked Spam"]),
            "OUTLOOK_CONFIG": ("Outlook Configuration", ["Outlook Profile Reset", "Autodiscover Issue"]),
            "EMAIL_FORWARDING": ("Forwarding / Rules", ["Auto-Forward Setup", "Mail Rule Issue"]),
            "MOBILE_MAIL": ("Mobile Email Setup", ["Mail Not Syncing on Mobile"]),
            "EMAIL_MIGRATION": ("Mailbox Migration", ["Mailbox Move Request"]),
            "EMAIL_ARCHIVING": ("Archiving / Retention", ["Archive Mailbox Request"]),
            "EMAIL_SIGNATURE": ("Signature / Branding", ["Signature Template Request"]),
        },
    },
    "LAPTOP_DESKTOP": {
        "name": "Laptop/Desktop",
        "subcategories": {
            "HW_FAILURE": ("Hardware Failure", ["Laptop Not Booting", "Screen/Keyboard Fault"]),
            "NEW_DEVICE": ("New Device Request", ["New Laptop Request", "New Desktop Request"]),
            "OS_ISSUE": ("Operating System Issue", ["OS Crash/BSOD", "Slow Performance"]),
            "SOFTWARE_INSTALL": ("Software Install/Update", ["Application Install Request", "Software Update Issue"]),
            "PERIPHERAL": ("Peripherals", ["Mouse/Keyboard/Dock Issue"]),
            "ENCRYPTION": ("Disk Encryption", ["BitLocker Issue", "Encryption Key Recovery"]),
            "ASSET_REPLACEMENT": ("Asset Replacement/Refresh", ["Device Refresh Request"]),
            "DOCKING_DISPLAY": ("Docking / External Display", ["Dual Monitor Setup Issue"]),
            "BATTERY": ("Battery / Power", ["Battery Replacement Request"]),
            "IMAGING": ("Device Imaging", ["Re-image Request"]),
            "MDM_ENROLLMENT": ("MDM Enrollment", ["Device Not Enrolling in MDM"]),
        },
    },
    "BACKUP": {
        "name": "Backup",
        "subcategories": {
            "BACKUP_FAILURE": ("Backup Job Failure", ["Backup Job Failed Alert"]),
            "RESTORE_REQUEST": ("Restore Request", ["File Restore Request", "Full System Restore Request"]),
            "BACKUP_POLICY": ("Backup Policy Change", ["Retention Policy Change Request"]),
            "BACKUP_CAPACITY": ("Backup Storage Capacity", ["Backup Storage Near Full"]),
            "BACKUP_NEW_SETUP": ("New Backup Setup", ["Onboard New Server to Backup"]),
            "TAPE_MGMT": ("Tape / Offsite Media", ["Tape Rotation Request"]),
            "BACKUP_VERIFICATION": ("Backup Verification", ["Restore Test Request"]),
        },
    },
    "LICENSE_MGMT": {
        "name": "License Management",
        "subcategories": {
            "SW_LICENSE_REQUEST": ("Software License Request", ["New License Request"]),
            "LICENSE_RENEWAL": ("License Renewal", ["Renewal Reminder Action"]),
            "LICENSE_COMPLIANCE": ("License Compliance", ["Compliance Audit Support"]),
            "LICENSE_REASSIGN": ("License Reassignment", ["Reassign License from Leaver"]),
            "M365_LICENSE": ("Microsoft 365 License", ["M365 License Assignment"]),
            "OS_LICENSE": ("OS License", ["Windows License Activation Issue"]),
            "VENDOR_CONTRACT": ("Vendor License Contract", ["Contract Renewal Coordination"]),
        },
    },
}