"""Loan scenario generator.

Creates a complete set of linked documents for a commercial real estate loan lifecycle.
All documents in a scenario share the same loan_id, client, and property data.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from faker import Faker

fake = Faker("nl_NL")


@dataclass
class Property:
    address: str
    city: str
    postal_code: str
    property_type: str
    year_built: int
    floor_area_sqm: int
    num_floors: int
    current_use: str
    proposed_use: str

    @staticmethod
    def generate() -> "Property":
        property_types = [
            "Office building",
            "Retail complex",
            "Mixed-use commercial",
            "Industrial warehouse",
            "Logistics center",
        ]
        uses = [
            ("Vacant office space", "Modern coworking facility"),
            ("Retail shops", "Mixed retail and residential"),
            ("Light industrial", "Tech startup campus"),
            ("Warehouse", "Last-mile logistics hub"),
            ("Office building", "Renovated grade-A office space"),
        ]
        current, proposed = fake.random_element(uses)
        return Property(
            address=fake.street_address(),
            city=fake.city(),
            postal_code=fake.postcode(),
            property_type=fake.random_element(property_types),
            year_built=fake.random_int(min=1960, max=2015),
            floor_area_sqm=fake.random_int(min=500, max=10000, step=100),
            num_floors=fake.random_int(min=1, max=12),
            current_use=current,
            proposed_use=proposed,
        )


@dataclass
class Client:
    company_name: str
    registration_number: str
    contact_name: str
    contact_title: str
    phone: str
    email: str
    address: str
    city: str
    postal_code: str
    years_in_business: int
    annual_revenue_eur: int

    @staticmethod
    def generate() -> "Client":
        company = fake.company()
        contact = fake.name()
        domain = company.lower().replace(" ", "").replace(".", "")
        email = f"{contact.split()[0].lower()}@{domain}.nl"
        return Client(
            company_name=company,
            registration_number=f"KVK-{fake.random_number(digits=8, fix_len=True)}",
            contact_name=contact,
            contact_title=fake.random_element(
                ["CEO", "CFO", "Managing Director", "Director of Finance"]
            ),
            phone=fake.phone_number(),
            email=email,
            address=fake.street_address(),
            city=fake.city(),
            postal_code=fake.postcode(),
            years_in_business=fake.random_int(min=2, max=40),
            annual_revenue_eur=fake.random_int(min=500_000, max=50_000_000, step=100_000),
        )


@dataclass
class LoanScenario:
    """A complete loan scenario with all linked data.

    Generate one of these, then pass it to each template to produce
    the full document chain for a single loan.
    """

    loan_id: str
    client: Client
    property: Property
    loan_amount_eur: int
    loan_term_years: int
    interest_rate_pct: float
    ltv_ratio_pct: float
    application_date: date
    valuation_date: date
    kyc_date: date
    contract_date: date
    invoice_date: date
    contractor_name: str
    contractor_kvk: str
    invoice_items: list[tuple[str, int]] = field(default_factory=list)

    @staticmethod
    def generate(base_date: date | None = None) -> "LoanScenario":
        """Generate a complete loan scenario with consistent, linked data."""
        if base_date is None:
            base_date = date.today() - timedelta(days=fake.random_int(min=30, max=365))

        client = Client.generate()
        prop = Property.generate()

        loan_amount = fake.random_int(min=1_000_000, max=20_000_000, step=250_000)
        property_value = int(loan_amount / fake.random_int(min=55, max=80) * 100)

        invoice_item_options = [
            ("Structural assessment and engineering report", 15_000),
            ("Architectural design services", 45_000),
            ("Demolition and site preparation", 80_000),
            ("Foundation reinforcement", 120_000),
            ("Electrical installation and rewiring", 65_000),
            ("HVAC system installation", 95_000),
            ("Plumbing and sanitary works", 55_000),
            ("Interior finishing and fit-out", 110_000),
            ("Fire safety system installation", 40_000),
            ("Facade renovation and insulation", 85_000),
            ("Elevator installation", 70_000),
            ("Landscaping and exterior works", 35_000),
            ("Project management fees", 25_000),
        ]
        num_items = fake.random_int(min=3, max=6)
        items = fake.random_elements(invoice_item_options, length=num_items, unique=True)
        # Add some variance to amounts
        items = [(desc, int(amt * fake.random_int(min=80, max=120) / 100)) for desc, amt in items]

        return LoanScenario(
            loan_id=f"CRE-{fake.random_number(digits=6, fix_len=True)}",
            client=client,
            property=prop,
            loan_amount_eur=loan_amount,
            loan_term_years=fake.random_element([5, 7, 10, 15, 20]),
            interest_rate_pct=round(fake.random_int(min=250, max=650) / 100, 2),
            ltv_ratio_pct=round(loan_amount / property_value * 100, 1),
            application_date=base_date,
            valuation_date=base_date + timedelta(days=fake.random_int(min=5, max=15)),
            kyc_date=base_date + timedelta(days=fake.random_int(min=7, max=20)),
            contract_date=base_date + timedelta(days=fake.random_int(min=25, max=45)),
            invoice_date=base_date + timedelta(days=fake.random_int(min=50, max=90)),
            contractor_name=fake.company(),
            contractor_kvk=f"KVK-{fake.random_number(digits=8, fix_len=True)}",
            invoice_items=items,
        )
