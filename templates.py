def apply_template(template_name: str, subject: str, body: str) -> str:
    base_style = """
    <style>
        body {
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
        }
        .container {
            padding: 20px;
        }
        .footer {
            margin-top: 30px;
            font-size: 12px;
            color: #888;
        }
    </style>
    """

    templates = {
        "corporate": (
            "",
            "Corporate Communications Department"
        ),
        "real_estate": (
            "🏡 ",
            "Real Estate & Property Services"
        ),
        "ecommerce": (
            "🛒 ",
            "Thank you for shopping with us 💙"
        ),
        "web3": (
            "🚀 ",
            "Powered by Web3 Infrastructure"
        ),
    }

    icon, footer = templates.get(template_name, ("", ""))
    html_body = body.replace("\n", "<br>")
    return f"""
    <html>
    <head>{base_style}</head>
    <body>
        <div class="container">
            <h2>{icon}{subject}</h2>
            <p>{html_body}</p>
            {f'<div class="footer">{footer}</div>' if footer else ""}
        </div>
    </body>
    </html>
    """