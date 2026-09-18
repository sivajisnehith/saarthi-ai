import base64
import os
import re
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
)


def generate_ticket_pdf(
    ticket: dict,
    output_dir: str = "generated_tickets",
) -> str:

    os.makedirs(output_dir, exist_ok=True)

    booking_reference = ticket["booking_reference"]

    # Keep filename safe.
    safe_reference = re.sub(
        r"[^A-Za-z0-9_-]",
        "_",
        booking_reference,
    )

    output_path = os.path.join(
        output_dir,
        f"ticket_{safe_reference}.pdf",
    )

    # -------------------------------------------------
    # PDF document
    # -------------------------------------------------

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TicketTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=22,
        spaceAfter=6,
    )

    subtitle_style = ParagraphStyle(
        "TicketSubtitle",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=11,
        spaceAfter=18,
    )

    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=13,
        spaceBefore=12,
        spaceAfter=8,
    )

    normal_style = ParagraphStyle(
        "TicketNormal",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
    )

    story = []

    # -------------------------------------------------
    # Header
    # -------------------------------------------------

    story.append(
        Paragraph(
            "SNEHITH TRAVELS",
            title_style,
        )
    )

    story.append(
        Paragraph(
            "Digital Bus Ticket",
            subtitle_style,
        )
    )

    # -------------------------------------------------
    # Booking information
    # -------------------------------------------------

    story.append(
        Paragraph(
            "Booking Details",
            heading_style,
        )
    )

    booking_data = [
        ["Booking Reference", booking_reference],
        ["Booking ID", str(ticket["booking_id"])],
        ["Status", ticket["status"]],
        ["Journey Date", ticket["journey_date"]],
    ]

    booking_table = Table(
        booking_data,
        colWidths=[45 * mm, 125 * mm],
    )

    booking_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    story.append(booking_table)

    # -------------------------------------------------
    # Journey information
    # -------------------------------------------------

    story.append(
        Paragraph(
            "Journey Details",
            heading_style,
        )
    )

    journey_data = [
        ["Bus", ticket["bus_name"]],
        ["Operator", ticket["operator"]],
        ["Bus Type", ticket["bus_type"]],
        ["Route", f'{ticket["origin"]} → {ticket["destination"]}'],
        ["Departure", ticket["departure_time"]],
        ["Arrival", ticket["arrival_time"]],
        ["Duration", ticket["duration"]],
        ["Boarding Point", ticket["boarding_point"]],
        ["Dropping Point", ticket["dropping_point"]],
    ]

    journey_table = Table(
        journey_data,
        colWidths=[45 * mm, 125 * mm],
    )

    journey_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    story.append(journey_table)

    # -------------------------------------------------
    # Passenger information
    # -------------------------------------------------

    story.append(
        Paragraph(
            "Passengers",
            heading_style,
        )
    )

    passenger_data = [
        [
            "Name",
            "Age",
            "Gender",
            "Seat",
        ]
    ]

    for passenger in ticket.get("passengers", []):

        passenger_data.append(
            [
                passenger["name"],
                str(passenger["age"]),
                passenger["gender"],
                passenger["seat_number"],
            ]
        )

    passenger_table = Table(
        passenger_data,
        colWidths=[
            70 * mm,
            25 * mm,
            35 * mm,
            40 * mm,
        ],
    )

    passenger_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    story.append(passenger_table)

    # -------------------------------------------------
    # Amount
    # -------------------------------------------------

    story.append(Spacer(1, 12))

    amount_data = [
        [
            Paragraph(
                "<b>Total Amount</b>",
                normal_style,
            ),
            Paragraph(
                f'<b>₹{ticket["total_amount"]:.2f}</b>',
                normal_style,
            ),
        ]
    ]

    amount_table = Table(
        amount_data,
        colWidths=[100 * mm, 70 * mm],
    )

    amount_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("BOX", (0, 0), (-1, -1), 1, colors.grey),
                ("PADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )

    story.append(amount_table)

    # -------------------------------------------------
    # QR code
    # -------------------------------------------------

    qr_code = ticket.get("qr_code")

    if qr_code:

        story.append(
            Paragraph(
                "Ticket QR Code",
                heading_style,
            )
        )

        try:

            if qr_code.startswith(
                "data:image/png;base64,"
            ):
                qr_code = qr_code.split(
                    ",",
                    1,
                )[1]

            qr_bytes = base64.b64decode(
                qr_code
            )

            qr_image = Image(
                BytesIO(qr_bytes),
                width=45 * mm,
                height=45 * mm,
            )

            qr_table = Table(
                [[qr_image]],
                colWidths=[170 * mm],
            )

            qr_table.setStyle(
                TableStyle(
                    [
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ]
                )
            )

            story.append(qr_table)

        except Exception as exc:

            story.append(
                Paragraph(
                    f"QR code could not be embedded: {exc}",
                    normal_style,
                )
            )

    # -------------------------------------------------
    # Footer
    # -------------------------------------------------

    story.append(Spacer(1, 15))

    story.append(
        Paragraph(
            "Please carry a valid ID and present this ticket "
            "when boarding.",
            subtitle_style,
        )
    )

    # -------------------------------------------------
    # Build PDF
    # -------------------------------------------------

    doc.build(story)

    return output_path