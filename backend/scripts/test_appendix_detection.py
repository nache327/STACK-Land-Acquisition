"""Quick smoke-test for appendix link detection."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bs4 import BeautifulSoup
from app.services.ordinance_fetcher import _find_appendix_links

html = """
<html><body>
  <a href="/Code/AxA-Table">Appendix A - Table of Permitted Uses</a>
  <a href="/Code/17.41">Chapter 17.41 Residential Zones</a>
  <a href="/Code/17.47">Chapter 17.47 Light Industrial</a>
  <a href="https://other.com/something">External link</a>
</body></html>
"""
soup = BeautifulSoup(html, "lxml")
links = _find_appendix_links(soup, "https://lindon.municipal.codes/Code/17")
print("Appendix links found:", links)
assert len(links) == 1
assert "AxA-Table" in links[0]
print("PASS: appendix link detection works correctly")
