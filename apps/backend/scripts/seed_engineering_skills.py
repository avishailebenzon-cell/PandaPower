#!/usr/bin/env python3
"""
Seed the canonical-skills library with a comprehensive set of skills used in
Israeli hi-tech & defense recruitment:

- Electronics engineering (analog, digital, RF, power, embedded)
- Test & measurement equipment (oscilloscopes, signal generators, etc.)
- EDA / CAD tools (Altium, OrCAD, KiCad, SPICE)
- Integration labs (HIL/SIL, EMI/EMC, environmental)
- Systems engineering (requirements, V-model, MBSE, V&V)
- Multi-disciplinary engineering (mechatronics, controls, vibration analysis)

Run:
    cd apps/backend
    PYTHONPATH=./src ./.venv/bin/python3 scripts/seed_engineering_skills.py

Idempotent: existing skills (matched by name, case-insensitive) are skipped.
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx

API_BASE = "http://localhost:8000"


# ─────────────────────────────────────────────────────────────────────────────
# Skill libraries
# ─────────────────────────────────────────────────────────────────────────────

# Each entry: (name, name_he, category, aliases, description)

ELECTRONICS_CORE = [
    # — Analog —
    ("Operational Amplifiers", "מגברי שרת", "Electronics", ["Op-Amp", "OpAmp", "Op Amps"], "Operational amplifier circuit design"),
    ("Amplifier Design", "תכנון מגברים", "Electronics", ["Amp Design"], "Linear amplifier topology and biasing"),
    ("Active Filters", "מסננים אקטיביים", "Electronics", ["Active Filter Design"], "Active filter topologies (Sallen-Key, MFB, etc.)"),
    ("Passive Filters", "מסננים פאסיביים", "Electronics", ["RC Filter", "LC Filter"], "Passive filter design"),
    ("Voltage Regulators", "ווסתי מתח", "Electronics", ["LDO", "Linear Regulator", "Switching Regulator"], "Linear & switching voltage regulators"),
    ("DC-DC Converters", "ממירי DC-DC", "Electronics", ["Buck", "Boost", "Buck-Boost", "SMPS"], "Switching DC-DC topologies"),
    ("Mixed Signal Design", "תכנון אותות מעורבים", "Electronics", ["Mixed-Signal"], "Combined analog/digital design"),
    ("ADC", "ממיר אנלוגי-דיגיטלי", "Electronics", ["A/D Converter", "Analog-to-Digital"], "Analog-to-digital conversion"),
    ("DAC", "ממיר דיגיטלי-אנלוגי", "Electronics", ["D/A Converter", "Digital-to-Analog"], "Digital-to-analog conversion"),
    ("PLL", "PLL", "Electronics", ["Phase-Locked Loop"], "Phase-locked loop design"),
    ("Crystal Oscillators", "מתנדי גביש", "Electronics", ["XTAL", "Quartz Oscillator"], "Crystal-based oscillator design"),
    ("Reference Voltage", "מתח רפרנס", "Electronics", ["Voltage Reference", "Bandgap"], "Precision voltage references"),

    # — Digital —
    ("Logic Design", "תכנון לוגי", "Electronics", ["Digital Logic", "Boolean Logic"], "Combinational and sequential logic"),
    ("State Machines", "מכונות מצב", "Electronics", ["FSM", "Finite State Machine"], "Finite state machine design"),
    ("VHDL", "VHDL", "Electronics", ["VHDL Programming"], "VHDL hardware description language"),
    ("Verilog", "Verilog", "Electronics", ["Verilog HDL"], "Verilog hardware description language"),
    ("SystemVerilog", "SystemVerilog", "Electronics", ["SV"], "SystemVerilog for design & verification"),
    ("CPLD", "CPLD", "Electronics", ["Complex Programmable Logic Device"], "Complex programmable logic devices"),
    ("ASIC Design", "תכנון ASIC", "Electronics", ["ASIC"], "Application-specific integrated circuit design"),
    ("Timing Analysis", "ניתוח זמנים", "Electronics", ["Static Timing Analysis", "STA"], "Static & dynamic timing analysis"),

    # — RF & microwave —
    ("RF Circuit Design", "תכנון מעגלי RF", "Electronics", ["Radio Frequency", "RF Design"], "RF & microwave circuit design"),
    ("Antenna Design", "תכנון אנטנות", "Electronics", ["Antennas"], "Antenna design and matching"),
    ("Microwave Engineering", "הנדסת מיקרוגל", "Electronics", ["Microwave"], "Microwave engineering"),
    ("Transmission Lines", "קווי תמסורת", "Electronics", ["TX Line", "Microstrip", "Stripline"], "Transmission line theory & design"),
    ("S-Parameters", "פרמטרי S", "Electronics", ["Scattering Parameters"], "S-parameter analysis"),
    ("Smith Chart", "מפת סמית", "Electronics", [], "Impedance matching using Smith charts"),
    ("Mixers", "מערבלים", "Electronics", ["RF Mixer"], "RF mixer design"),
    ("LNA Design", "תכנון מגברי רעש נמוך", "Electronics", ["Low Noise Amplifier"], "Low-noise amplifier design"),
    ("Power Amplifiers", "מגברי הספק", "Electronics", ["PA", "RF PA"], "RF power amplifier design"),

    # — Power —
    ("Switching Power Supplies", "ספקי כוח מיתוג", "Electronics", ["SMPS", "Switch Mode Power Supply"], "Switching power supply design"),
    ("Linear Power Supplies", "ספקי כוח לינאריים", "Electronics", ["Linear PSU"], "Linear power supply design"),
    ("Thermal Management", "ניהול תרמי", "Electronics", ["Heat Sink Design", "Thermal Design"], "Heat sink and thermal management"),
    ("EMI/EMC", "EMI/EMC", "Electronics", ["EMC", "EMI", "ElectroMagnetic Compatibility"], "Electromagnetic compatibility / interference"),
    ("Battery Management", "ניהול סוללות", "Electronics", ["BMS", "Battery Management System"], "Battery management systems"),
    ("Motor Control", "בקרת מנועים", "Electronics", ["Motor Drive", "BLDC Control"], "DC, BLDC and stepper motor control"),

    # — Communications & protocols —
    ("UART", "UART", "Electronics", ["Serial Communication"], "UART serial protocol"),
    ("SPI", "SPI", "Electronics", ["Serial Peripheral Interface"], "SPI protocol"),
    ("I2C", "I2C", "Electronics", ["IIC", "I²C"], "I²C protocol"),
    ("CAN Bus", "CAN Bus", "Electronics", ["CAN", "Controller Area Network"], "Controller Area Network protocol"),
    ("LIN Bus", "LIN Bus", "Electronics", ["LIN"], "Local Interconnect Network"),
    ("MIL-STD-1553", "MIL-STD-1553", "Electronics", ["1553", "1553B"], "Military 1553 data bus"),
    ("ARINC 429", "ARINC 429", "Electronics", ["ARINC429"], "Avionics ARINC 429 bus"),
    ("Ethernet", "Ethernet", "Electronics", ["IEEE 802.3"], "Ethernet networking"),
    ("RS-232", "RS-232", "Electronics", ["RS232"], "RS-232 serial protocol"),
    ("RS-485", "RS-485", "Electronics", ["RS485"], "RS-485 differential serial"),
    ("USB", "USB", "Electronics", ["Universal Serial Bus"], "USB protocol design"),
    ("PCIe", "PCIe", "Electronics", ["PCI Express"], "PCI Express bus"),
    ("DDR Memory Interface", "ממשק זיכרון DDR", "Electronics", ["DDR3", "DDR4", "DDR5"], "DDR memory interface design"),
]

ELECTRONICS_CAD_TOOLS = [
    ("Altium Designer", "Altium Designer", "Electronics", ["Altium", "Altium PCB"], "Altium Designer PCB CAD tool"),
    ("OrCAD", "OrCAD", "Electronics", ["OrCAD Capture"], "Cadence OrCAD schematic & PCB"),
    ("Allegro PCB", "Allegro PCB", "Electronics", ["Cadence Allegro"], "Cadence Allegro PCB layout"),
    ("KiCad", "KiCad", "Electronics", ["KiCAD"], "Open-source PCB CAD"),
    ("Mentor PADS", "Mentor PADS", "Electronics", ["PADS", "PADS Logic"], "Mentor PADS PCB design"),
    ("Mentor Xpedition", "Mentor Xpedition", "Electronics", ["Xpedition"], "Mentor Xpedition Enterprise"),
    ("Eagle PCB", "Eagle PCB", "Electronics", ["Eagle CAD"], "Autodesk Eagle PCB"),
    ("LTspice", "LTspice", "Electronics", ["LTSpice", "SPICE"], "LTspice circuit simulation"),
    ("PSpice", "PSpice", "Electronics", ["Cadence PSpice"], "PSpice circuit simulation"),
    ("Cadence Virtuoso", "Cadence Virtuoso", "Electronics", ["Virtuoso"], "Cadence Virtuoso analog IC design"),
    ("ADS", "ADS", "Electronics", ["Advanced Design System", "Keysight ADS"], "Keysight Advanced Design System (RF)"),
    ("HFSS", "HFSS", "Electronics", ["Ansys HFSS"], "Ansys HFSS electromagnetic simulator"),
    ("CST Studio", "CST Studio", "Electronics", ["CST Microwave Studio"], "CST Studio Suite EM simulator"),
    ("Microwave Office", "Microwave Office", "Electronics", ["AWR MWO"], "Cadence AWR Microwave Office"),
    ("MATLAB", "MATLAB", "Electronics", ["Matlab"], "MATLAB numerical computing"),
    ("Simulink", "Simulink", "Electronics", ["MATLAB Simulink"], "Simulink model-based design"),
    ("Quartus", "Quartus", "Electronics", ["Intel Quartus", "Quartus Prime"], "Intel/Altera Quartus FPGA tools"),
    ("Vivado", "Vivado", "Electronics", ["Xilinx Vivado"], "Xilinx Vivado FPGA development suite"),
    ("ISE", "ISE", "Electronics", ["Xilinx ISE"], "Xilinx ISE (legacy FPGA tools)"),
    ("ModelSim", "ModelSim", "Electronics", ["QuestaSim"], "ModelSim HDL simulator"),
]

LAB_TEST_EQUIPMENT = [
    ("Oscilloscope Operation", "הפעלת אוסצילוסקופ", "Lab Equipment", ["Scope", "DSO", "MSO"], "Digital storage oscilloscope operation"),
    ("Logic Analyzer", "מנתח לוגי", "Lab Equipment", ["LA"], "Logic analyzer operation"),
    ("Spectrum Analyzer", "מנתח ספקטרום", "Lab Equipment", ["SA"], "Spectrum analyzer operation"),
    ("Network Analyzer", "מנתח רשתות", "Lab Equipment", ["VNA", "Vector Network Analyzer"], "Vector network analyzer (S-parameters)"),
    ("Signal Generator", "גנרטור אותות", "Lab Equipment", ["Function Generator", "Arbitrary Waveform Generator", "AWG"], "Signal/function/arbitrary waveform generators"),
    ("Bench Power Supply", "ספק כח שולחני", "Lab Equipment", ["DC Power Supply", "Lab PSU"], "Bench DC power supply operation"),
    ("Electronic Load", "עומס אלקטרוני", "Lab Equipment", ["E-Load", "DC Load"], "Programmable electronic load"),
    ("Fluke Multimeter", "מולטימטר Fluke", "Lab Equipment", ["Fluke", "Fluke DMM"], "Fluke handheld multimeters"),
    ("DMM", "מולטימטר דיגיטלי", "Lab Equipment", ["Digital Multimeter"], "Bench-top digital multimeter"),
    ("LCR Meter", "מד LCR", "Lab Equipment", ["LCR"], "Inductance/capacitance/resistance meter"),
    ("Frequency Counter", "מד תדר", "Lab Equipment", [], "Frequency counter operation"),
    ("Power Meter", "מד הספק", "Lab Equipment", ["RF Power Meter"], "RF power meter operation"),
    ("Noise Figure Meter", "מד פיגור רעש", "Lab Equipment", ["NF Meter"], "Noise figure measurement"),
    ("BERT", "BERT", "Lab Equipment", ["Bit Error Rate Tester"], "Bit error rate testing"),
    ("Protocol Analyzer", "מנתח פרוטוקול", "Lab Equipment", [], "Protocol analyzers (CAN, MIL-1553, ARINC)"),
    ("Thermal Chamber", "תא תרמי", "Lab Equipment", ["Environmental Chamber", "Climate Chamber"], "Thermal/environmental test chamber"),
    ("Shaker Table", "שולחן רעידות", "Lab Equipment", ["Vibration Table"], "Vibration test shaker"),
    ("Anechoic Chamber", "חדר אנקואיים", "Lab Equipment", ["EMC Chamber"], "EMC/RF anechoic chamber"),
    ("ESD Gun", "אקדח ESD", "Lab Equipment", ["ElectroStatic Discharge Gun"], "ESD susceptibility testing"),
    ("Soldering Station", "תחנת הלחמה", "Lab Equipment", ["Reflow", "Hot Air Station"], "Soldering & rework station operation"),
    ("Microscope (Inspection)", "מיקרוסקופ", "Lab Equipment", ["PCB Inspection Microscope"], "Inspection microscope for PCB work"),
    ("Curve Tracer", "מתחקה אופייני", "Lab Equipment", [], "Semiconductor curve tracer"),
    ("Data Acquisition", "איסוף נתונים", "Lab Equipment", ["DAQ", "Data Acquisition System"], "DAQ systems & instrumentation"),
    ("LabVIEW", "LabVIEW", "Lab Equipment", ["NI LabVIEW", "VI"], "NI LabVIEW for instrumentation control"),
    ("TestStand", "TestStand", "Lab Equipment", ["NI TestStand"], "NI TestStand test sequencer"),
    ("PXI", "PXI", "Lab Equipment", ["PXI Modular Test"], "PXI modular instrumentation"),
    ("GPIB / IEEE-488", "GPIB", "Lab Equipment", ["IEEE-488", "GPIB Interface"], "GPIB instrument control"),
    ("SCPI", "SCPI", "Lab Equipment", ["Standard Commands for Programmable Instruments"], "SCPI instrument command language"),
    ("Calibration", "כיול", "Lab Equipment", ["Metrology"], "Equipment calibration & metrology"),
]

SYSTEMS_ENGINEERING = [
    # — Requirements & analysis —
    ("Requirements Engineering", "הנדסת דרישות", "Systems Engineering", ["Requirements Analysis"], "Requirements elicitation, analysis & management"),
    ("Requirements Management", "ניהול דרישות", "Systems Engineering", ["DOORS", "Jama"], "Requirements management tools (DOORS, Jama)"),
    ("DOORS", "DOORS", "Systems Engineering", ["IBM DOORS", "DOORS Next"], "IBM DOORS requirements tool"),
    ("Use Cases", "מקרי שימוש", "Systems Engineering", ["Use Case Analysis"], "Use case modeling"),
    ("CONOPS", "CONOPS", "Systems Engineering", ["Concept of Operations"], "Concept of Operations document"),
    ("Stakeholder Analysis", "ניתוח בעלי עניין", "Systems Engineering", [], "Stakeholder identification & needs analysis"),

    # — Architecture —
    ("Systems Architecture", "ארכיטקטורת מערכות", "Systems Engineering", ["System Architecture"], "System-level architecture design"),
    ("MBSE", "MBSE", "Systems Engineering", ["Model-Based Systems Engineering", "SysML"], "Model-based systems engineering"),
    ("SysML", "SysML", "Systems Engineering", ["Systems Modeling Language"], "Systems Modeling Language"),
    ("UML", "UML", "Systems Engineering", ["Unified Modeling Language"], "Unified Modeling Language"),
    ("Cameo Systems Modeler", "Cameo Systems Modeler", "Systems Engineering", ["Cameo", "MagicDraw"], "Cameo / MagicDraw MBSE tool"),
    ("Capella", "Capella", "Systems Engineering", ["Arcadia", "Eclipse Capella"], "Arcadia method / Capella MBSE tool"),
    ("Enterprise Architect", "Enterprise Architect", "Systems Engineering", ["Sparx EA"], "Sparx Enterprise Architect"),
    ("ICD", "ICD", "Systems Engineering", ["Interface Control Document"], "Interface Control Document authoring"),
    ("Interface Design", "תכנון ממשקים", "Systems Engineering", ["Interface Definition"], "System interface design"),

    # — Process & lifecycle —
    ("V-Model", "מודל V", "Systems Engineering", ["V Model", "Vee Model"], "V-model development lifecycle"),
    ("Waterfall", "Waterfall", "Systems Engineering", ["Waterfall Model"], "Waterfall development model"),
    ("System Lifecycle", "מחזור חיי מערכת", "Systems Engineering", ["SLC", "Systems Engineering Lifecycle"], "System engineering lifecycle management"),
    ("Trade Studies", "ניתוחי trade-off", "Systems Engineering", ["Trade-off Analysis"], "Trade studies and decision analysis"),
    ("Risk Management", "ניהול סיכונים", "Systems Engineering", ["Risk Analysis"], "Risk identification, analysis & mitigation"),
    ("FMEA", "FMEA", "Systems Engineering", ["Failure Mode and Effects Analysis"], "Failure Mode and Effects Analysis"),
    ("FTA", "FTA", "Systems Engineering", ["Fault Tree Analysis"], "Fault tree analysis"),
    ("Reliability Engineering", "הנדסת אמינות", "Systems Engineering", ["MTBF", "Reliability Prediction"], "Reliability, MTBF & availability analysis"),
    ("Safety Analysis", "ניתוח בטיחות", "Systems Engineering", ["System Safety"], "System safety analysis"),
    ("Hazard Analysis", "ניתוח סיכונים", "Systems Engineering", ["HAZOP"], "Hazard analysis (HAZOP, etc.)"),

    # — Verification & validation —
    ("Verification & Validation", "אימות ותיקוף", "Systems Engineering", ["V&V", "Verification and Validation"], "V&V planning and execution"),
    ("Test Plans", "תכניות בדיקה", "Systems Engineering", ["Test Planning"], "Test plan development"),
    ("Acceptance Testing", "בדיקות קבלה", "Systems Engineering", ["FAT", "Factory Acceptance Test"], "Factory & site acceptance testing"),
    ("Integration Testing", "בדיקות שילוב", "Systems Engineering", [], "System integration test campaigns"),
    ("Qualification Testing", "בדיקות הסמכה", "Systems Engineering", ["Qual Testing"], "Environmental & qualification testing"),
    ("Configuration Management", "ניהול תצורה", "Systems Engineering", ["CM", "Configuration Control"], "Configuration management discipline"),

    # — Standards (defense + commercial) —
    ("DO-178C", "DO-178C", "Systems Engineering", ["DO178", "DO-178B"], "DO-178C airborne software certification"),
    ("DO-254", "DO-254", "Systems Engineering", ["DO254"], "DO-254 airborne hardware certification"),
    ("ARP4754A", "ARP4754A", "Systems Engineering", ["ARP-4754"], "ARP4754A development of civil aircraft systems"),
    ("MIL-STD-810", "MIL-STD-810", "Systems Engineering", ["810G", "810H"], "Environmental engineering standard"),
    ("MIL-STD-461", "MIL-STD-461", "Systems Engineering", ["461F", "461G"], "EMI/EMC requirements for military equipment"),
    ("MIL-STD-704", "MIL-STD-704", "Systems Engineering", [], "Aircraft electric power characteristics"),
    ("ISO 26262", "ISO 26262", "Systems Engineering", ["Functional Safety Automotive"], "Automotive functional safety"),
    ("IEC 61508", "IEC 61508", "Systems Engineering", ["SIL"], "Functional safety of E/E/PE systems"),
    ("IEEE 15288", "IEEE 15288", "Systems Engineering", ["ISO 15288"], "Systems and software engineering lifecycle processes"),
    ("ECSS Standards", "תקני ECSS", "Systems Engineering", ["ECSS"], "European space engineering standards"),

    # — Multi-disciplinary —
    ("Mechatronics", "מכטרוניקה", "Systems Engineering", [], "Combined mechanical-electrical-software design"),
    ("Control Systems", "מערכות בקרה", "Systems Engineering", ["Controls Engineering"], "Closed-loop control system design"),
    ("Servo Systems", "מערכות סרבו", "Systems Engineering", ["Servo Control"], "Servo motor control systems"),
    ("Sensor Fusion", "מיזוג חיישנים", "Systems Engineering", [], "Multi-sensor data fusion"),
    ("Kalman Filter", "מסנן קלמן", "Systems Engineering", ["EKF", "UKF"], "Kalman filter design"),
    ("Image Processing", "עיבוד תמונה", "Systems Engineering", ["Computer Vision"], "Image processing and computer vision"),
    ("Optics", "אופטיקה", "Systems Engineering", ["Optical Systems"], "Optical engineering basics"),
    ("Vibration Analysis", "ניתוח רעידות", "Systems Engineering", ["Modal Analysis"], "Mechanical vibration analysis"),
    ("Thermal Analysis", "ניתוח תרמי", "Systems Engineering", ["CFD", "Heat Transfer"], "Thermal/CFD analysis"),
    ("RAMS", "RAMS", "Systems Engineering", ["Reliability Availability Maintainability Safety"], "RAMS engineering (railway/transport)"),
    ("ILS / Logistics", "תמיכה לוגיסטית משולבת", "Systems Engineering", ["Integrated Logistics Support", "LSA"], "Integrated logistics support"),
    ("Human Factors Engineering", "הנדסת גורמי אנוש", "Systems Engineering", ["HFE", "Ergonomics"], "Human factors / ergonomics"),
]

INTEGRATION_LAB = [
    ("HIL", "HIL", "Integration Labs", ["Hardware-In-the-Loop"], "Hardware-in-the-loop simulation"),
    ("SIL", "SIL", "Integration Labs", ["Software-In-the-Loop"], "Software-in-the-loop simulation"),
    ("MIL", "MIL", "Integration Labs", ["Model-In-the-Loop"], "Model-in-the-loop simulation"),
    ("System Integration", "אינטגרציית מערכת", "Integration Labs", ["Sys Integration"], "Multi-system integration"),
    ("Integration Test", "בדיקות אינטגרציה", "Integration Labs", ["Integration Testing"], "Integration test execution"),
    ("Environmental Testing", "בדיקות סביבתיות", "Integration Labs", ["Env Test"], "Vibration, thermal, humidity testing"),
    ("EMC Testing", "בדיקות EMC", "Integration Labs", ["EMC Test", "EMI Test"], "EMC/EMI compliance testing"),
    ("Stress Testing", "בדיקות עומס", "Integration Labs", ["HALT", "HASS"], "HALT/HASS accelerated stress testing"),
    ("Burn-In Testing", "Burn-In", "Integration Labs", ["Burn In"], "Burn-in test procedures"),
    ("Automated Test", "בדיקה אוטומטית", "Integration Labs", ["ATE", "Automated Test Equipment"], "Automated test equipment & frameworks"),
    ("Test Automation", "אוטומציית בדיקות", "Integration Labs", ["Test Scripting"], "Test automation framework development"),
    ("Lab Management", "ניהול מעבדה", "Integration Labs", ["Lab Coordinator"], "Lab operations management"),
]


ALL_SKILLS = ELECTRONICS_CORE + ELECTRONICS_CAD_TOOLS + LAB_TEST_EQUIPMENT + SYSTEMS_ENGINEERING + INTEGRATION_LAB


# ─────────────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────────────


async def main():
    payload = {
        "skills": [
            {
                "name": name,
                "name_he": name_he,
                "category": cat,
                "aliases": aliases or [],
                "description": desc,
            }
            for (name, name_he, cat, aliases, desc) in ALL_SKILLS
        ]
    }

    print(f"Submitting {len(payload['skills'])} skills to {API_BASE}/admin/skills/bulk-add ...")
    by_cat = {}
    for s in payload["skills"]:
        by_cat[s["category"]] = by_cat.get(s["category"], 0) + 1
    for cat, n in sorted(by_cat.items()):
        print(f"  {cat}: {n}")
    print()

    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{API_BASE}/admin/skills/bulk-add", json=payload)
        if r.status_code != 200:
            print(f"ERROR HTTP {r.status_code}: {r.text[:500]}")
            sys.exit(1)
        result = r.json()

    print(f"✓ Submitted: {result['submitted']}")
    print(f"✓ Created:   {result['created']}")
    print(f"⊙ Skipped duplicates: {result['skipped_duplicates']}")
    if result.get("errors_count"):
        print(f"✗ Errors: {result['errors_count']}")
        for e in result.get("errors", [])[:10]:
            print(f"    - {e}")


if __name__ == "__main__":
    asyncio.run(main())
