"""PDF document templates for commercial real estate loan scenarios.

Each template function takes a LoanScenario and returns the PDF content
as bytes. Templates use fpdf2 for PDF generation and Faker (nl_NL) for
supplementary realistic text in narrative sections.

Templates:
    - loan_application:  Structured application form (Confidential)
    - valuation_report:  Narrative property valuation (Confidential)
    - kyc_report:        Due diligence / KYC report (Secret)
    - contract:          Loan agreement with legal clauses (Secret)
    - invoice:           Contractor invoice (Public)
"""

from __future__ import annotations

from datetime import timedelta

from faker import Faker
from fpdf import FPDF

from generator.scenario import LoanScenario

fake = Faker("nl_NL")


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


class _BasePDF(FPDF):
    """Shared PDF base with header/footer behaviour."""

    classification: str = ""
    loan_id: str = ""

    def header(self) -> None:
        self.set_font("Helvetica", "B", 8)
        self.cell(
            0,
            5,
            f"Classification: {self.classification}",
            align="L",
        )
        self.ln(0)
        self.cell(0, 5, f"Loan ID: {self.loan_id}", align="R")
        self.ln(6)
        self.set_draw_color(180, 180, 180)
        self.set_line_width(0.3)
        self.line(
            self.l_margin,
            self.get_y(),
            self.w - self.r_margin,
            self.get_y(),
        )
        self.ln(4)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "I", 7)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")


def _new_pdf(classification: str, loan_id: str) -> _BasePDF:
    """Create a pre-configured PDF instance."""
    pdf = _BasePDF(orientation="P", unit="mm", format="A4")
    pdf.classification = classification
    pdf.loan_id = loan_id
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(left=20, top=20, right=20)
    return pdf


def _section_heading(pdf: FPDF, title: str) -> None:
    """Render a bold section heading with a subtle underline."""
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
    y = pdf.get_y()
    pdf.set_draw_color(100, 100, 100)
    pdf.set_line_width(0.2)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(3)


def _body_text(pdf: FPDF, text: str) -> None:
    """Render a paragraph of body text."""
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5, text)
    pdf.ln(2)


def _label_value(pdf: FPDF, label: str, value: str) -> None:
    """Render a label: value pair on a single line."""
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(55, 6, f"{label}:", align="L")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")


def _fmt_eur(amount: int | float) -> str:
    """Format a euro amount with thousands separator."""
    return f"EUR {amount:,.0f}"


def _pick(options: list[str]) -> str:
    """Pick a random element from *options* via Faker."""
    return fake.random_element(options)


# -------------------------------------------------------------------
# 1. Loan Application  (Confidential, ~1 page)
# -------------------------------------------------------------------


def generate_loan_application(scenario: LoanScenario) -> bytes:
    """Generate a structured loan application form.

    A concise, form-style document capturing client details, property
    information, and the requested loan parameters.
    """
    pdf = _new_pdf("Confidential", scenario.loan_id)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(
        0,
        12,
        "Commercial Real Estate Loan Application",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)

    # Application metadata
    app_date = scenario.application_date.strftime("%d %B %Y")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(
        0,
        5,
        f"Date: {app_date}",
        align="R",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)

    # --- Client Details ---
    c = scenario.client
    _section_heading(pdf, "1. Client Details")
    _label_value(pdf, "Company Name", c.company_name)
    _label_value(pdf, "Registration No.", c.registration_number)
    _label_value(pdf, "Contact Person", c.contact_name)
    _label_value(pdf, "Title", c.contact_title)
    _label_value(pdf, "Phone", c.phone)
    _label_value(pdf, "Email", c.email)
    _label_value(
        pdf,
        "Address",
        f"{c.address}, {c.postal_code} {c.city}",
    )
    _label_value(pdf, "Years in Business", str(c.years_in_business))
    _label_value(
        pdf,
        "Annual Revenue",
        _fmt_eur(c.annual_revenue_eur),
    )
    pdf.ln(4)

    # --- Property Details ---
    p = scenario.property
    _section_heading(pdf, "2. Property Details")
    _label_value(
        pdf,
        "Property Address",
        f"{p.address}, {p.postal_code} {p.city}",
    )
    _label_value(pdf, "Property Type", p.property_type)
    _label_value(pdf, "Year Built", str(p.year_built))
    _label_value(pdf, "Floor Area", f"{p.floor_area_sqm:,} sqm")
    _label_value(pdf, "Number of Floors", str(p.num_floors))
    _label_value(pdf, "Current Use", p.current_use)
    _label_value(pdf, "Proposed Use", p.proposed_use)
    pdf.ln(4)

    # --- Loan Details ---
    _section_heading(pdf, "3. Loan Request")
    _label_value(
        pdf,
        "Loan Amount Requested",
        _fmt_eur(scenario.loan_amount_eur),
    )
    _label_value(pdf, "Loan Term", f"{scenario.loan_term_years} years")
    _label_value(
        pdf,
        "Proposed Interest Rate",
        f"{scenario.interest_rate_pct:.2f}%",
    )
    _label_value(
        pdf,
        "Loan-to-Value Ratio",
        f"{scenario.ltv_ratio_pct:.1f}%",
    )
    purpose = (
        f"Acquisition and renovation of {p.property_type.lower()} "
        f"for conversion to {p.proposed_use.lower()}"
    )
    _label_value(pdf, "Purpose", purpose)
    pdf.ln(6)

    # --- Declaration ---
    _section_heading(pdf, "4. Declaration")
    _body_text(
        pdf,
        "The undersigned hereby declares that all information provided "
        "in this application is true, complete, and accurate to the "
        "best of their knowledge. The applicant authorises Rabobank to "
        "obtain any additional information required for the assessment "
        "of this application, including credit bureau checks and "
        "property valuations.",
    )
    pdf.ln(8)

    # Signature block
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(80, 6, "Signature: ___________________________")
    pdf.cell(
        0,
        6,
        f"Date: {app_date}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)
    pdf.cell(80, 6, f"Name: {c.contact_name}")
    pdf.cell(
        0,
        6,
        f"Title: {c.contact_title}",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    return pdf.output()


# -------------------------------------------------------------------
# 2. Valuation Report  (Confidential, ~2-3 pages)
# -------------------------------------------------------------------


def generate_valuation_report(scenario: LoanScenario) -> bytes:
    """Generate a narrative property valuation report.

    A text-heavy report written in the style of a professional property
    surveyor, covering the property description, location, condition,
    market analysis, risk factors, and final valuation conclusion.
    """
    pdf = _new_pdf("Confidential", scenario.loan_id)
    pdf.add_page()

    prop = scenario.property
    client = scenario.client
    property_value = int(scenario.loan_amount_eur / scenario.ltv_ratio_pct * 100)
    val_date = scenario.valuation_date.strftime("%d %B %Y")

    # Title
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(
        0,
        12,
        "Property Valuation Report",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0,
        6,
        f"Valuation Date: {val_date}",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(
        0,
        6,
        f"Prepared for: {client.company_name}",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(6)

    # --- Executive Summary ---
    _section_heading(pdf, "1. Executive Summary")
    _body_text(
        pdf,
        f"This report presents the findings of an independent valuation "
        f"of the commercial property located at {prop.address}, "
        f"{prop.postal_code} {prop.city}. The valuation has been "
        f"conducted in accordance with Royal Institution of Chartered "
        f"Surveyors (RICS) standards and the European Valuation "
        f"Standards (EVS) to support a financing request submitted by "
        f"{client.company_name}. The property was inspected on "
        f"{val_date} and all observations are based on conditions as "
        f"of that date.",
    )
    _body_text(
        pdf,
        f"Based on our analysis, the estimated market value of the "
        f"subject property is {_fmt_eur(property_value)}. This "
        f"valuation reflects the property's current condition, "
        f"location attributes, comparable transactions in the area, "
        f"and prevailing market conditions for "
        f"{prop.property_type.lower()} properties in {prop.city} "
        f"and the surrounding region.",
    )

    # --- Property Description ---
    _section_heading(pdf, "2. Property Description")
    structure = _pick(
        [
            "reinforced concrete frame",
            "steel frame with concrete core",
            "load-bearing masonry",
        ]
    )
    roofing = _pick(
        [
            "flat bituminous",
            "pitched tile",
            "green-roof system",
        ]
    )
    floors_s = "s" if prop.num_floors > 1 else ""
    _body_text(
        pdf,
        f"The subject property is a {prop.property_type.lower()} "
        f"originally constructed in {prop.year_built}. It comprises "
        f"{prop.num_floors} floor{floors_s} with a total gross "
        f"lettable area of approximately {prop.floor_area_sqm:,} "
        f"square metres. The building is currently used as "
        f"{prop.current_use.lower()}, though the applicant intends "
        f"to convert it into {prop.proposed_use.lower()}. The "
        f"structure features {structure} construction with {roofing} "
        f"roofing.",
    )
    ground_floor = _pick(
        [
            "an open-plan reception area with meeting rooms",
            "commercial retail frontage with storage to the rear",
            "loading bays and a goods-receiving area",
        ]
    )
    upper_floors = _pick(
        [
            "partitioned office suites served by two passenger lifts",
            "open warehouse space with mezzanine storage levels",
            "a combination of office and light-industrial units",
        ]
    )
    parking = _pick(
        [
            "dedicated underground",
            "surface-level",
            "adjacent multi-storey",
        ]
    )
    num_vehicles = fake.random_int(min=20, max=150)
    mep_year = fake.random_int(min=2005, max=2020)
    mep_systems = _pick(
        [
            "central air conditioning, fire suppression, and BMS controls",
            "gas-fired central heating and partial mechanical ventilation",
            "VRV climate control with smart building management",
        ]
    )
    _body_text(
        pdf,
        f"Internally, the ground floor provides {ground_floor}. "
        f"Upper floors consist of {upper_floors}. The building has "
        f"{parking} parking accommodating approximately "
        f"{num_vehicles} vehicles. Mechanical and electrical systems "
        f"were last updated in {mep_year} and include {mep_systems}.",
    )

    # --- Location Analysis ---
    _section_heading(pdf, "3. Location Analysis")
    district = _pick(
        [
            "well-established commercial district",
            "rapidly developing mixed-use quarter",
            "prominent industrial zone on the urban fringe",
        ]
    )
    transport = _pick(
        [
            "the A-ring motorway network",
            "major regional arterial roads",
            "the national rail network",
        ]
    )
    train_min = fake.random_int(min=1, max=15)
    growth = _pick(
        [
            "steady population growth and rising demand for commercial space",
            "significant infrastructure investment over the past decade",
            "increasing interest from institutional investors in recent years",
        ]
    )
    vacancy = fake.random_int(min=3, max=18)
    vacancy_comment = _pick(
        [
            "which is below the national average and indicative of a tight market",
            "reflecting a market that is gradually recovering from the pandemic-era correction",
        ]
    )
    _body_text(
        pdf,
        f"The property is situated in {prop.city}, a {district} "
        f"with good access to {transport} and public transport. The "
        f"nearest train station is approximately {train_min} minutes "
        f"on foot. {prop.city} has seen {growth}. Vacancy rates for "
        f"comparable {prop.property_type.lower()} properties in the "
        f"area currently stand at approximately {vacancy}%, "
        f"{vacancy_comment}.",
    )
    amenities = _pick(
        [
            "several restaurants, a hotel, and a conference centre",
            "a shopping centre, fitness facilities, and childcare services",
            "business parks housing major corporate tenants",
        ]
    )
    zoning = _pick(
        [
            "commercial and office use with limited residential permissibility",
            "mixed-use development including retail, office, and housing",
            "industrial and logistics purposes with provisions for ancillary office space",
        ]
    )
    _body_text(
        pdf,
        f"Nearby amenities include {amenities}. The municipality's "
        f"zoning plan designates the area for {zoning}.",
    )

    # --- Condition Assessment ---
    _section_heading(pdf, "4. Condition Assessment")
    condition = _pick(["generally good", "satisfactory", "fair"])
    defect = _pick(
        [
            "minor cracking in partition walls",
            "surface spalling on external concrete elements",
            "localised dampness in basement areas",
        ]
    )
    _body_text(
        pdf,
        f"A thorough inspection of the property was carried out on "
        f"{val_date}. The structural elements of the building, "
        f"including foundations, load-bearing walls, and floor slabs, "
        f"were found to be in {condition} condition for a building of "
        f"this age. No significant structural defects were observed, "
        f"though some {defect} was noted.",
    )
    mep_state = _pick(
        [
            "operational but approaching end-of-life",
            "in adequate working condition with regular maintenance records available",
            "partially upgraded and functional",
        ]
    )
    roof_state = _pick(
        [
            "normal wear consistent with its age",
            "recent patching that suggests a history of water ingress",
            "good maintenance with no active leaks detected",
        ]
    )
    epc_label = _pick(["C", "D", "E", "F"])
    _body_text(
        pdf,
        f"The mechanical and electrical installations are "
        f"{mep_state}. The roof shows signs of {roof_state}. An "
        f"energy performance certificate rated the building at label "
        f"{epc_label}, and upgrading to at least label C may be "
        f"required under forthcoming Dutch regulations.",
    )

    # --- Market Analysis ---
    _section_heading(pdf, "5. Market Analysis")
    avg_rent = fake.random_int(min=80, max=250)
    yield_pct = round(fake.random_int(min=400, max=800) / 100, 2)
    market_trend = _pick(
        [
            "moderate growth over the past two years, underpinned by "
            "improving economic fundamentals",
            "a period of stabilisation following several years of price correction",
            "strong investor interest driven by yield compression in prime locations",
        ]
    )
    _body_text(
        pdf,
        f"The {prop.property_type.lower()} market in {prop.city} "
        f"and the broader region has experienced {market_trend}. "
        f"Average asking rents for comparable properties range from "
        f"{_fmt_eur(avg_rent - 30)} to {_fmt_eur(avg_rent + 30)} "
        f"per square metre per annum, while net initial yields for "
        f"recent transactions have been observed between "
        f"{yield_pct - 0.5:.2f}% and {yield_pct + 0.5:.2f}%.",
    )
    num_comps = fake.random_int(min=3, max=8)
    val_lo = _fmt_eur(int(property_value * 0.92))
    val_hi = _fmt_eur(int(property_value * 1.08))
    _body_text(
        pdf,
        f"We identified {num_comps} comparable transactions within "
        f"a 10-kilometre radius completed in the past eighteen "
        f"months. After adjusting for location, size, condition, and "
        f"lease profile, these comparables support a value range of "
        f"{val_lo} to {val_hi} for the subject property. Our "
        f"valuation of {_fmt_eur(property_value)} sits comfortably "
        f"within this range.",
    )

    # --- Risk Factors ---
    _section_heading(pdf, "6. Risk Factors")

    # Environmental risk paragraphs — varied severity and subtlety.
    # Some use explicit terms ("contamination"), others use contextual
    # language that only a semantic classifier would associate with
    # environmental risk ("polder", "below NAP", "former dye works").
    env_paragraph = _pick(
        [
            (
                "From an environmental perspective, the site has a "
                "documented history of industrial activity. Records "
                "indicate that a chemical processing facility operated "
                "on the adjacent parcel from 1958 to 1992, and soil "
                "sampling conducted in 2018 revealed elevated "
                "concentrations of heavy metals and polycyclic aromatic "
                "hydrocarbons in the topsoil layer. A Phase II "
                "Environmental Site Assessment is strongly recommended "
                "before any financing commitment. Remediation costs, "
                "if required, could be substantial and would directly "
                "affect the viability of the proposed development."
            ),
            (
                "The property is situated in a designated polder area, "
                "approximately 1.8 metres below Normaal Amsterdams Peil "
                "(NAP). The local water board (waterschap) maintains "
                "active pumping infrastructure to manage groundwater "
                "levels in this zone. While this is standard for much "
                "of the western Netherlands, prospective lenders should "
                "note that climate projections indicate increased "
                "precipitation intensity and rising sea levels, which "
                "may place additional strain on water management systems "
                "in low-lying areas over the loan term."
            ),
            (
                f"Historical records indicate that the building was "
                f"constructed during a period when asbestos-containing "
                f"materials were routinely used in insulation, floor "
                f"tiles, and pipe lagging. A limited asbestos survey "
                f"conducted in 2019 identified chrysotile-containing "
                f"materials in the ceiling void of the second floor. "
                f"Full removal prior to renovation is a legal "
                f"requirement under Dutch regulations and will add "
                f"approximately {_fmt_eur(fake.random_int(min=50_000, max=200_000, step=10_000))} "
                f"to the project budget."
            ),
            (
                "The site is located adjacent to what was formerly a "
                "textile dyeing and finishing works, which ceased "
                "operations in 1997. While the subject property itself "
                "was not used for industrial purposes, groundwater "
                "migration from the neighbouring site remains a "
                "concern. The municipality has classified the area as "
                "a monitored zone under the Wet bodembescherming (Soil "
                "Protection Act), and any ground disturbance during "
                "renovation may trigger mandatory environmental "
                "monitoring requirements."
            ),
            (
                "The property is located in an area with no significant "
                "history of industrial use. The surrounding neighbourhood "
                "is predominantly residential and commercial. No "
                "environmental concerns have been identified in the "
                "municipal environmental registry (bodemloket) for this "
                "parcel. Standard due diligence is recommended but no "
                "specific environmental risks are anticipated."
            ),
            (
                "The site borders a canal that forms part of the "
                "regional waterway network. Historical usage of the "
                "canal for barge transport of bulk materials, including "
                "petroleum products and building aggregates, has "
                "resulted in localised sediment contamination along the "
                "quay walls. While the building itself is set back from "
                "the waterline, any foundation work extending below the "
                "current water table will require dewatering permits and "
                "environmental monitoring of discharge water quality."
            ),
        ]
    )
    _body_text(
        pdf,
        f"Several risk factors should be considered in relation to this valuation. {env_paragraph}",
    )

    _body_text(
        pdf,
        "Changes to Dutch environmental regulations, including "
        "stricter energy-efficiency requirements under the BENG "
        "standards, could necessitate additional capital expenditure "
        "that is not reflected in the current valuation.",
    )
    demand_level = _pick(["robust", "reasonable", "moderate"])
    _body_text(
        pdf,
        f"Market risk is also a relevant consideration. While "
        f"current demand for {prop.property_type.lower()} space in "
        f"{prop.city} is {demand_level}, the market is sensitive to "
        f"macroeconomic headwinds, including potential interest-rate "
        f"increases by the European Central Bank and shifting "
        f"occupier demand due to remote-working trends. A "
        f"deterioration in market conditions could reduce achievable "
        f"rents and extend void periods, thereby compressing the "
        f"property's income-based valuation.",
    )
    building_age = scenario.valuation_date.year - prop.year_built
    replacement_years = fake.random_int(min=3, max=8)
    capex = _fmt_eur(fake.random_int(min=200_000, max=800_000, step=50_000))
    _body_text(
        pdf,
        f"From a structural standpoint, the building's age "
        f"({building_age} years) means that significant components, "
        f"including the roof membrane, elevator systems, and HVAC "
        f"plant, may require replacement within the next "
        f"{replacement_years} years. The estimated cost of such "
        f"capital works is in the range of {capex}, which "
        f"prospective lenders should factor into their risk "
        f"assessment. Additionally, the planned conversion from "
        f"{prop.current_use.lower()} to {prop.proposed_use.lower()} "
        f"is subject to municipal planning approval, and there is "
        f"no guarantee that such consent will be granted without "
        f"conditions or delay.",
    )

    # --- Valuation Conclusion ---
    _section_heading(pdf, "7. Valuation Conclusion")
    _body_text(
        pdf,
        f"Having regard to the foregoing analysis, and in accordance "
        f"with RICS Valuation Global Standards, we are of the "
        f"opinion that the market value of the freehold interest in "
        f"the property at {prop.address}, {prop.postal_code} "
        f"{prop.city}, as at {val_date}, is:",
    )
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(
        0,
        10,
        _fmt_eur(property_value),
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0,
        6,
        f"({_words_from_amount(property_value)})",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(6)

    _body_text(
        pdf,
        "This valuation is provided for secured lending purposes and "
        "is addressed to Rabobank. It is subject to the assumptions, "
        "caveats, and limiting conditions set out in the appendices "
        "to this report. The valuation should be reviewed no later "
        "than twelve months from the date of inspection.",
    )
    pdf.ln(6)

    # Surveyor sign-off
    surveyor = fake.name()
    firm = fake.company()
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0,
        6,
        f"Prepared by: {surveyor}, MRICS",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(
        0,
        6,
        f"Firm: {firm} Vastgoedwaardering B.V.",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(
        0,
        6,
        f"Date: {val_date}",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    return pdf.output()


def _words_from_amount(amount: int) -> str:
    """Return a simple textual description of a euro amount."""
    millions = amount / 1_000_000
    if millions >= 1:
        return f"approximately {millions:,.1f} million euros"
    thousands = amount / 1_000
    return f"approximately {thousands:,.0f} thousand euros"


# -------------------------------------------------------------------
# 3. KYC Report  (Secret, ~1-2 pages)
# -------------------------------------------------------------------


def generate_kyc_report(scenario: LoanScenario) -> bytes:
    """Generate a Know Your Customer / due diligence report.

    A narrative report covering client background, ownership
    structure, source of funds, AML screening, risk assessment, and
    recommendation.
    """
    pdf = _new_pdf("Secret", scenario.loan_id)
    pdf.add_page()

    client = scenario.client
    kyc_date = scenario.kyc_date.strftime("%d %B %Y")

    # Title
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(
        0,
        12,
        "Know Your Customer Report",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0,
        6,
        f"Assessment Date: {kyc_date}",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(
        0,
        6,
        f"Subject: {client.company_name} ({client.registration_number})",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(6)

    # --- Client Overview ---
    _section_heading(pdf, "1. Client Overview")
    company_type = _pick(
        [
            "privately held",
            "family-owned",
            "limited liability",
        ]
    )
    num_staff = fake.random_int(min=10, max=500)
    num_offices = fake.random_int(min=1, max=5)
    office_s = "s" if num_offices > 1 else ""
    _body_text(
        pdf,
        f"{client.company_name} is a {company_type} company "
        f"registered with the Dutch Chamber of Commerce under number "
        f"{client.registration_number}. The company has been in "
        f"continuous operation for {client.years_in_business} years "
        f"and is headquartered at {client.address}, "
        f"{client.postal_code} {client.city}. The principal contact "
        f"for this engagement is {client.contact_name}, serving as "
        f"{client.contact_title}. The company reported annual "
        f"revenue of {_fmt_eur(client.annual_revenue_eur)} in the "
        f"most recent fiscal year and employs approximately "
        f"{num_staff} staff across "
        f"{num_offices} office{office_s}.",
    )

    # --- Ownership Structure ---
    _section_heading(pdf, "2. Ownership Structure")
    ubo_name = fake.name()
    ubo_pct = fake.random_int(min=51, max=100)
    minority_note = (
        "The remaining shares are held by minority investors who have been identified and screened."
        if ubo_pct < 100
        else "There are no other shareholders."
    )
    nationality = _pick(
        [
            "Dutch national",
            "Dutch resident with EU nationality",
            "naturalised Dutch citizen",
        ]
    )
    _body_text(
        pdf,
        f"The ultimate beneficial owner (UBO) of "
        f"{client.company_name} is {ubo_name}, holding {ubo_pct}% "
        f"of the issued share capital. {minority_note} The UBO is a "
        f"{nationality} and has been verified through a copy of a "
        f"valid identity document (passport) and a recent extract "
        f"from the Kamer van Koophandel (KvK). No adverse "
        f"information was found regarding {ubo_name} in public "
        f"records or media sources.",
    )

    # --- Source of Funds ---
    _section_heading(pdf, "3. Source of Funds")
    equity_source = _pick(
        [
            "retained earnings accumulated over the past several financial years",
            "the sale of a previously held commercial property portfolio",
            "a capital injection by the principal shareholder from documented personal wealth",
        ]
    )
    _body_text(
        pdf,
        f"The funds for the proposed transaction will be sourced "
        f"from a combination of the requested bank financing "
        f"({_fmt_eur(scenario.loan_amount_eur)}) and the client's "
        f"own equity contribution. The equity component is derived "
        f"from {equity_source}. Bank statements covering the "
        f"preceding twelve months have been reviewed and are "
        f"consistent with the declared source of funds. No unusual "
        f"patterns of activity were identified.",
    )

    # --- AML Screening Results ---
    _section_heading(pdf, "4. AML Screening Results")
    _body_text(
        pdf,
        "The client entity, its UBO, and all associated parties "
        "have been screened against applicable sanctions lists, "
        "including the EU Consolidated Sanctions List, the Dutch "
        "national sanctions register, OFAC SDN, and the UN Security "
        "Council Consolidated List. No matches were found. A "
        "Politically Exposed Person (PEP) screening was also "
        "conducted with negative results. Adverse media screening "
        "using Dow Jones and World-Check databases returned no "
        "material findings.",
    )
    dd_level = _pick(["standard", "enhanced"])
    _body_text(
        pdf,
        f"Transaction monitoring thresholds have been set in "
        f"accordance with the Wwft (Wet ter voorkoming van "
        f"witwassen en financieren van terrorisme). The client "
        f"relationship has been classified as {dd_level} due "
        f"diligence, consistent with the risk profile described "
        f"below.",
    )

    # --- Risk Assessment ---
    _section_heading(pdf, "5. Risk Assessment")
    risk_level = _pick(["Low", "Medium-Low", "Medium"])
    sector = _pick(
        [
            "commercial real estate",
            "property development",
            "construction and renovation",
        ]
    )
    inherent_risk = _pick(["moderate", "low-to-moderate"])
    amount_note = (
        "within normal parameters for this client segment"
        if scenario.loan_amount_eur < 10_000_000
        else "at the upper end for this client segment, warranting periodic review"
    )
    _body_text(
        pdf,
        f"The overall KYC risk rating for {client.company_name} is "
        f"assessed as {risk_level}. This rating considers the "
        f"following factors: the client operates in the {sector} "
        f"sector, which carries an inherent {inherent_risk} risk of "
        f"money laundering. The client's jurisdiction (the "
        f"Netherlands) is a low-risk country with a well-developed "
        f"regulatory framework. The transaction amount "
        f"({_fmt_eur(scenario.loan_amount_eur)}) is {amount_note}. "
        f"No adverse information or unexplained wealth indicators "
        f"were identified during the assessment.",
    )

    # --- Recommendation ---
    _section_heading(pdf, "6. Recommendation")
    review_cycle = "twelve months" if risk_level == "Medium" else "twenty-four months"
    _body_text(
        pdf,
        f"Based on the due diligence procedures performed, it is "
        f"recommended that the client relationship with "
        f"{client.company_name} be approved for the purpose of the "
        f"proposed loan facility. The client meets all regulatory "
        f"requirements under the Wwft and internal compliance "
        f"policies. A periodic review should be scheduled in "
        f"accordance with the {risk_level.lower()}-risk review "
        f"cycle ({review_cycle}).",
    )
    pdf.ln(6)

    # Sign-off
    analyst = fake.name()
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0,
        6,
        f"Analyst: {analyst}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(
        0,
        6,
        "Department: Financial Crime Compliance",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(
        0,
        6,
        f"Date: {kyc_date}",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    return pdf.output()


# -------------------------------------------------------------------
# 4. Contract  (Secret, ~3-4 pages)
# -------------------------------------------------------------------


def generate_contract(scenario: LoanScenario) -> bytes:
    """Generate a loan agreement with formal legal clauses.

    A comprehensive loan contract with numbered articles covering
    parties, definitions, loan terms, interest and repayment,
    collateral, covenants, events of default, and governing law.
    """
    pdf = _new_pdf("Secret", scenario.loan_id)
    pdf.add_page()

    client = scenario.client
    prop = scenario.property
    property_value = int(scenario.loan_amount_eur / scenario.ltv_ratio_pct * 100)
    monthly_payment = _calc_monthly_payment(
        scenario.loan_amount_eur,
        scenario.interest_rate_pct,
        scenario.loan_term_years,
    )
    contract_date = scenario.contract_date.strftime("%d %B %Y")
    val_date = scenario.valuation_date.strftime("%d %B %Y")
    drawdown_deadline = (scenario.contract_date + timedelta(days=30)).strftime("%d %B %Y")

    # Title
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(
        0,
        12,
        "Loan Agreement",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0,
        6,
        f"Execution Date: {contract_date}",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(
        0,
        6,
        f"Reference: {scenario.loan_id}",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(6)

    # --- Article 1: Parties ---
    _section_heading(pdf, "Article 1 - Parties")
    _body_text(
        pdf,
        f'1.1  This Loan Agreement (the "Agreement") is entered '
        f"into on {contract_date} by and between:",
    )
    _body_text(
        pdf,
        "(a)  Rabobank N.V., a public limited company incorporated "
        "under the laws of the Netherlands, having its registered "
        "office at Croeselaan 18, 3521 CB Utrecht, registered with "
        "the Dutch Chamber of Commerce under number KVK-30046259 "
        '(hereinafter referred to as the "Lender");',
    )
    _body_text(
        pdf,
        f"(b)  {client.company_name}, a private limited company "
        f"incorporated under the laws of the Netherlands, having "
        f"its registered office at {client.address}, "
        f"{client.postal_code} {client.city}, registered with the "
        f"Dutch Chamber of Commerce under number "
        f"{client.registration_number} (hereinafter referred to as "
        f'the "Borrower").',
    )
    _body_text(
        pdf,
        "The Lender and the Borrower are hereinafter collectively "
        'referred to as the "Parties" and individually as a '
        '"Party".',
    )

    # --- Article 2: Definitions ---
    _section_heading(pdf, "Article 2 - Definitions")
    _body_text(
        pdf,
        "2.1  In this Agreement, unless the context otherwise "
        "requires, the following terms shall have the meanings set "
        "out below:",
    )
    definitions = [
        (
            '"Business Day"',
            "a day (other than a Saturday or Sunday) on which "
            "banks are open for general business in Amsterdam;",
        ),
        (
            '"Drawdown Date"',
            f"the date on which the Loan is advanced to the "
            f"Borrower, being no later than {drawdown_deadline};",
        ),
        (
            '"Loan"',
            f"the principal sum of "
            f"{_fmt_eur(scenario.loan_amount_eur)} made available "
            f"by the Lender to the Borrower under this Agreement;",
        ),
        (
            '"Maturity Date"',
            f"the date falling {scenario.loan_term_years} years after the Drawdown Date;",
        ),
        (
            '"Property"',
            f"the commercial real estate located at "
            f"{prop.address}, {prop.postal_code} {prop.city}, as "
            f"further described in Article 5;",
        ),
        (
            '"Security"',
            "the mortgage and other security interests created "
            "pursuant to Article 5 of this Agreement.",
        ),
    ]
    for _, (term, definition) in enumerate(definitions, start=1):
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(55, 5, f"  {term}")
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5, definition)
        pdf.ln(1)

    # --- Article 3: Loan Terms ---
    _section_heading(pdf, "Article 3 - Loan Terms")
    _body_text(
        pdf,
        f"3.1  Subject to the terms and conditions of this "
        f"Agreement, the Lender agrees to make available to the "
        f"Borrower a term loan facility in the aggregate principal "
        f"amount of {_fmt_eur(scenario.loan_amount_eur)} (the "
        f'"Facility").',
    )
    _body_text(
        pdf,
        f"3.2  The Facility shall be drawn in a single advance on "
        f"the Drawdown Date. The term of the Facility is "
        f"{scenario.loan_term_years} years from the Drawdown Date.",
    )
    _body_text(
        pdf,
        f"3.3  The purpose of the Facility is to finance the "
        f"acquisition and renovation of the Property for conversion "
        f"from {prop.current_use.lower()} to "
        f"{prop.proposed_use.lower()}. The Borrower shall not use "
        f"the proceeds of the Facility for any other purpose "
        f"without the prior written consent of the Lender.",
    )

    # --- Article 4: Interest and Repayment ---
    _section_heading(pdf, "Article 4 - Interest and Repayment")
    _body_text(
        pdf,
        f"4.1  The Loan shall bear interest at a fixed rate of "
        f"{scenario.interest_rate_pct:.2f}% per annum, calculated "
        f"on the basis of a 360-day year and the actual number of "
        f"days elapsed.",
    )
    _body_text(
        pdf,
        "4.2  Interest shall be payable monthly in arrears on the "
        "first Business Day of each calendar month, commencing on "
        "the first such date following the Drawdown Date.",
    )
    _body_text(
        pdf,
        f"4.3  The Borrower shall repay the Loan in equal monthly "
        f"instalments of {_fmt_eur(monthly_payment)} (inclusive of "
        f"principal and interest) over the term of the Facility, "
        f"with any remaining balance due and payable on the "
        f"Maturity Date.",
    )
    _body_text(
        pdf,
        "4.4  The Borrower may prepay all or part of the "
        "outstanding Loan upon thirty (30) days' prior written "
        "notice to the Lender, subject to a prepayment fee equal "
        "to 1% of the amount prepaid if such prepayment occurs "
        "within the first three (3) years of the Facility.",
    )
    _body_text(
        pdf,
        "4.5  In the event of late payment, default interest shall "
        "accrue on the overdue amount at a rate of 2% per annum "
        "above the rate specified in Article 4.1, compounded "
        "monthly.",
    )

    # --- Article 5: Collateral ---
    _section_heading(pdf, "Article 5 - Collateral")
    _body_text(
        pdf,
        f"5.1  As security for the due and punctual performance of "
        f"all obligations of the Borrower under this Agreement, the "
        f"Borrower shall grant to the Lender a first-ranking "
        f"mortgage (hypotheekrecht) over the Property located at "
        f"{prop.address}, {prop.postal_code} {prop.city}.",
    )
    _body_text(
        pdf,
        f"5.2  The Property has been independently valued at "
        f"{_fmt_eur(property_value)} as of {val_date}, resulting in "
        f"a loan-to-value ratio of {scenario.ltv_ratio_pct:.1f}%. "
        f"The Borrower shall ensure that the loan-to-value ratio "
        f"does not exceed 80% at any time during the term of the "
        f"Facility. Should the ratio exceed this threshold, the "
        f"Borrower shall, within sixty (60) days, either reduce "
        f"the outstanding principal or provide additional security "
        f"acceptable to the Lender.",
    )
    _body_text(
        pdf,
        "5.3  The Borrower shall maintain comprehensive insurance "
        "coverage on the Property, including fire, storm, flood, "
        "and public liability insurance, with the Lender noted as "
        "loss payee. Evidence of insurance shall be provided to "
        "the Lender annually.",
    )

    # --- Article 6: Covenants ---
    _section_heading(pdf, "Article 6 - Covenants")
    _body_text(
        pdf,
        "6.1  The Borrower covenants and undertakes that, for so "
        "long as any amount remains outstanding under this "
        "Agreement, the Borrower shall:",
    )
    covenants = [
        "maintain a debt service coverage ratio of not less than 1.20x, tested quarterly;",
        "provide the Lender with audited annual financial "
        "statements within one hundred and twenty (120) days of "
        "the end of each financial year;",
        "not create or permit to subsist any lien, charge, or "
        "encumbrance on the Property other than the mortgage "
        "created in favour of the Lender;",
        "not dispose of, transfer, or otherwise deal with the "
        "Property or any material part thereof without the prior "
        "written consent of the Lender;",
        "comply with all applicable laws, regulations, and "
        "permits, including environmental and planning "
        "regulations;",
        "promptly notify the Lender of any event which "
        "constitutes or may constitute an Event of Default.",
    ]
    for i, covenant in enumerate(covenants, start=1):
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(10, 5, f"  ({chr(96 + i)})")
        pdf.multi_cell(0, 5, covenant)
        pdf.ln(1)

    # --- Article 7: Events of Default ---
    _section_heading(pdf, "Article 7 - Events of Default")
    _body_text(
        pdf,
        "7.1  Each of the following events shall constitute an "
        "Event of Default under this Agreement:",
    )
    defaults = [
        "the Borrower fails to make any payment due under this "
        "Agreement within five (5) Business Days of its due date;",
        "any representation or warranty made by the Borrower "
        "proves to have been materially incorrect or misleading "
        "when made;",
        "the Borrower breaches any covenant set out in Article 6 "
        "and, where such breach is capable of remedy, fails to "
        "remedy it within thirty (30) days of notice from the "
        "Lender;",
        "the Borrower becomes insolvent, enters into "
        "administration, or commences winding-up proceedings;",
        "the value of the Property, as determined by an "
        "independent valuation commissioned by the Lender, "
        "declines by more than 20% from the valuation date, and "
        "the Borrower fails to provide additional security within "
        "sixty (60) days of notice.",
    ]
    for i, default in enumerate(defaults, start=1):
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(10, 5, f"  ({chr(96 + i)})")
        pdf.multi_cell(0, 5, default)
        pdf.ln(1)

    _body_text(
        pdf,
        "7.2  Upon the occurrence of an Event of Default, the "
        "Lender may, by written notice to the Borrower, declare "
        "all outstanding amounts under this Agreement to be "
        "immediately due and payable and proceed to enforce the "
        "Security.",
    )

    # --- Article 8: Governing Law ---
    _section_heading(
        pdf,
        "Article 8 - Governing Law and Jurisdiction",
    )
    _body_text(
        pdf,
        "8.1  This Agreement and any non-contractual obligations "
        "arising out of or in connection with it shall be governed "
        "by and construed in accordance with the laws of the "
        "Netherlands.",
    )
    _body_text(
        pdf,
        "8.2  The courts of Amsterdam shall have exclusive "
        "jurisdiction to settle any dispute arising out of or in "
        "connection with this Agreement.",
    )
    _body_text(
        pdf,
        "8.3  This Agreement constitutes the entire agreement "
        "between the Parties with respect to its subject matter "
        "and supersedes all prior negotiations, representations, "
        "and agreements, whether written or oral.",
    )
    pdf.ln(6)

    # --- Signatures ---
    _section_heading(pdf, "Signatures")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(85, 6, "For and on behalf of the Lender:")
    pdf.cell(
        0,
        6,
        "For and on behalf of the Borrower:",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(8)
    pdf.cell(85, 6, "___________________________")
    pdf.cell(
        0,
        6,
        "___________________________",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(2)
    lender_sig = fake.name()
    pdf.cell(85, 6, f"Name: {lender_sig}")
    pdf.cell(
        0,
        6,
        f"Name: {client.contact_name}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(85, 6, "Title: Director Commercial Real Estate")
    pdf.cell(
        0,
        6,
        f"Title: {client.contact_title}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(85, 6, f"Date: {contract_date}")
    pdf.cell(
        0,
        6,
        f"Date: {contract_date}",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    return pdf.output()


def _calc_monthly_payment(
    principal: int,
    annual_rate_pct: float,
    term_years: int,
) -> int:
    """Calculate a fixed monthly mortgage payment (annuity)."""
    r = annual_rate_pct / 100 / 12
    n = term_years * 12
    if r == 0:
        return int(principal / n)
    payment = principal * r * (1 + r) ** n / ((1 + r) ** n - 1)
    return int(payment)


# -------------------------------------------------------------------
# 5. Invoice  (Public, ~1 page)
# -------------------------------------------------------------------


def generate_invoice(scenario: LoanScenario) -> bytes:
    """Generate a contractor invoice for renovation works.

    A structured invoice with line items, subtotal, VAT, and grand
    total, formatted as a professional business document.
    """
    pdf = _new_pdf("Public", scenario.loan_id)
    pdf.add_page()

    client = scenario.client
    prop = scenario.property
    inv_date = scenario.invoice_date.strftime("%d %B %Y")

    # Title
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(
        0,
        12,
        "INVOICE",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(6)

    # Invoice metadata
    inv_num = f"INV-{scenario.loan_id.replace('CRE-', '')}-001"
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0,
        6,
        f"Invoice No: {inv_num}",
        align="R",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(
        0,
        6,
        f"Date: {inv_date}",
        align="R",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)

    # From / To blocks
    col_w = (pdf.w - pdf.l_margin - pdf.r_margin) / 2
    y_start = pdf.get_y()

    # FROM
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(col_w, 6, "From:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        col_w,
        5,
        scenario.contractor_name,
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(
        col_w,
        5,
        f"KvK: {scenario.contractor_kvk}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(
        col_w,
        5,
        fake.street_address(),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(
        col_w,
        5,
        f"{fake.postcode()} {fake.city()}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    y_after_from = pdf.get_y()

    # TO (positioned on the right)
    pdf.set_y(y_start)
    pdf.set_x(pdf.l_margin + col_w)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(col_w, 6, "To:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(pdf.l_margin + col_w)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        col_w,
        5,
        client.company_name,
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.set_x(pdf.l_margin + col_w)
    pdf.cell(
        col_w,
        5,
        f"KvK: {client.registration_number}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.set_x(pdf.l_margin + col_w)
    pdf.cell(
        col_w,
        5,
        client.address,
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.set_x(pdf.l_margin + col_w)
    pdf.cell(
        col_w,
        5,
        f"{client.postal_code} {client.city}",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    pdf.set_y(max(y_after_from, pdf.get_y()) + 4)

    # Reference
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(25, 6, "Re:")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0,
        6,
        f"Renovation works at {prop.address}, {prop.postal_code} {prop.city}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(6)

    # --- Line items table ---
    table_w = pdf.w - pdf.l_margin - pdf.r_margin
    desc_w = table_w * 0.70
    amt_w = table_w * 0.30

    # Header row
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(desc_w, 8, "  Description", border=1, fill=True)
    pdf.cell(
        amt_w,
        8,
        "Amount",
        border=1,
        fill=True,
        align="R",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    # Line items
    pdf.set_font("Helvetica", "", 10)
    subtotal = 0
    for description, amount in scenario.invoice_items:
        subtotal += amount
        pdf.cell(
            desc_w,
            7,
            f"  {description}",
            border="LR",
        )
        pdf.cell(
            amt_w,
            7,
            _fmt_eur(amount),
            border="LR",
            align="R",
            new_x="LMARGIN",
            new_y="NEXT",
        )

    # Close table body
    pdf.set_draw_color(0, 0, 0)
    pdf.line(
        pdf.l_margin,
        pdf.get_y(),
        pdf.l_margin + table_w,
        pdf.get_y(),
    )
    pdf.ln(2)

    # Totals
    vat_rate = 0.21
    vat_amount = int(subtotal * vat_rate)
    grand_total = subtotal + vat_amount

    totals_x = pdf.l_margin + desc_w - 40
    label_w = 40.0
    val_w = amt_w

    pdf.set_font("Helvetica", "", 10)
    pdf.set_x(totals_x)
    pdf.cell(label_w, 7, "Subtotal:", align="R")
    pdf.cell(
        val_w,
        7,
        _fmt_eur(subtotal),
        align="R",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    pdf.set_x(totals_x)
    pdf.cell(label_w, 7, "VAT (21%):", align="R")
    pdf.cell(
        val_w,
        7,
        _fmt_eur(vat_amount),
        align="R",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    # Grand total with emphasis
    pdf.set_x(totals_x)
    y_line = pdf.get_y()
    pdf.line(
        totals_x + label_w,
        y_line,
        totals_x + label_w + val_w,
        y_line,
    )
    pdf.ln(1)

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_x(totals_x)
    pdf.cell(label_w, 8, "Total Due:", align="R")
    pdf.cell(
        val_w,
        8,
        _fmt_eur(grand_total),
        align="R",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(8)

    # Payment terms
    _section_heading(pdf, "Payment Terms")
    iban = fake.iban()
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0,
        6,
        "Payment is due within 30 days of the invoice date.",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(
        0,
        6,
        f"Bank: Rabobank  |  IBAN: {iban}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.cell(
        0,
        6,
        f"Reference: {inv_num}",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    return pdf.output()


# -------------------------------------------------------------------
# Document type registry
# -------------------------------------------------------------------

DOCUMENT_TYPES: dict[str, dict] = {
    "loan_application": {
        "generator": generate_loan_application,
        "classification": "Confidential",
    },
    "valuation_report": {
        "generator": generate_valuation_report,
        "classification": "Confidential",
    },
    "kyc_report": {
        "generator": generate_kyc_report,
        "classification": "Secret",
    },
    "contract": {
        "generator": generate_contract,
        "classification": "Secret",
    },
    "invoice": {
        "generator": generate_invoice,
        "classification": "Public",
    },
}
