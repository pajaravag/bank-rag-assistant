from src.scraper.cleaner import clean_html


def test_strips_icon_tokens_and_cta_lines():
    html = """
    <html><head><title>Página</title></head><body><main>
      <p>El factoring permite anticipar el pago de tus facturas.</p>
      <span>angle-right-small</span>
      <a>Conocer más</a>
      <p>Aplica para pymes y grandes empresas.</p>
    </main></body></html>
    """
    title, text = clean_html(html)
    assert title == "Página"
    assert "factoring" in text
    assert "angle-right-small" not in text
    assert "Conocer más" not in text


def test_deduplicates_repeated_blocks():
    html = """
    <html><body><main>
      <div><p>Bloque de campaña repetido en carrusel.</p></div>
      <div><p>Bloque de campaña repetido en carrusel.</p></div>
      <p>Contenido único.</p>
    </main></body></html>
    """
    _, text = clean_html(html)
    assert text.count("Bloque de campaña repetido en carrusel.") == 1
    assert "Contenido único." in text


def test_removes_boilerplate_tags():
    html = """
    <html><body>
      <nav><a>Menú principal</a></nav>
      <main><p>Contenido real de la página bancaria.</p></main>
      <footer><p>Pie de página legal.</p></footer>
      <script>var x = 1;</script>
    </body></html>
    """
    _, text = clean_html(html)
    assert "Contenido real" in text
    assert "Menú principal" not in text
    assert "Pie de página" not in text
    assert "var x" not in text
