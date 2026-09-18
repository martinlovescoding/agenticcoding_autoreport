"""The one property no unit test can see: the page fits the screen it is opened on.

Everything else about the page is structural — a slot either rendered or it did not.
Layout is not. A grid *track* floors at its items' min-content width and a grid *item*
floors at its own, so a table whose cells are `white-space: nowrap` widens its whole
column, and the running text laid out beside it, past the viewport. Nothing in the
markup is wrong; the page simply scrolls sideways, and reading it means panning. That is
a browser measurement or it is nothing.

Chrome will not open a window narrower than about 500 CSS pixels, so the report is
measured inside a 400px iframe instead — the width the artifact contract names, and the
narrowest screen the page has to hold. Skipped where no browser is installed, because a
missing browser is not a failure of the page.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from agenticcoding import cli

PHONE_WIDTH = 400
DESKTOP_WIDTH = 1280

_BROWSERS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "chromium",
    "chromium-browser",
)

# Measures the page as the reader's screen would: inside a frame of a known width, with
# the document's own scroll width read back out. `--allow-file-access-from-files` is what
# lets the wrapper read the frame it loaded.
_WRAPPER = """<!doctype html>
<meta charset="utf-8">
<title>measuring</title>
<iframe id="frame" src="{page}" style="width:{width}px;height:2000px;border:0"></iframe>
<script>
  var frame = document.getElementById("frame");
  function measure() {{
    var root = frame.contentDocument.documentElement;
    document.title = "w" + root.scrollWidth + "," + root.clientWidth;
  }}
  frame.addEventListener("load", measure);
  if (frame.contentDocument && frame.contentDocument.readyState === "complete") measure();
</script>
"""


def _browser() -> str | None:
    for candidate in _BROWSERS:
        if Path(candidate).exists():
            return candidate
        found = shutil.which(candidate)
        if found:
            return found
    return None


@pytest.fixture(scope="module")
def browser() -> str:
    found = _browser()
    if found is None:
        pytest.skip("no Chrome or Chromium on this machine to measure layout with")
    return found


@pytest.fixture(scope="module")
def page(tmp_path_factory) -> Path:
    """A real report of a real dataset — a short page would not overflow."""
    directory = tmp_path_factory.mktemp("layout")
    raw, report = directory / "raw.csv", directory / "report.html"
    cli.main(["generate", "--rows", "200", "--out", str(raw)])
    cli.main(["report", "--input", str(raw), "--out", str(report), "--as-of", "2026-09-18"])
    return report


def measure(browser: str, page: Path, width: int) -> tuple[int, int]:
    """`(scroll width, viewport width)` of the report inside a `width`-wide frame."""
    wrapper = page.with_name(f"wrapper-{width}.html")
    wrapper.write_text(_WRAPPER.format(page=page.name, width=width), encoding="utf-8")
    dumped = subprocess.run(
        [
            browser, "--headless", "--disable-gpu", "--hide-scrollbars",
            "--allow-file-access-from-files",
            "--window-size=1400,900", "--virtual-time-budget=4000",
            "--dump-dom", wrapper.as_uri(),
        ],
        capture_output=True, text=True, timeout=120, check=True,
    ).stdout
    match = re.search(r"<title>w(\d+),(\d+)</title>", dumped)
    assert match, "the measurement never ran — the frame did not load"
    return int(match.group(1)), int(match.group(2))


# A chart is authored in a 720-unit viewBox and scaled to whatever width it is given, so
# its type shrinks with it: the 11px axis numbers on a phone-width card come out at about
# 5px, which is not a smaller number — it is a smudge. The fix is a floor on the chart's
# rendered width, so this measures the type as the reader gets it: the chart's rendered
# width over its viewBox width, times the smallest font size inside it.
_PROBE = """<!doctype html>
<meta charset="utf-8">
<title>measuring</title>
<iframe id="frame" src="{page}" style="width:{width}px;height:3000px;border:0"></iframe>
<script>
  var frame = document.getElementById("frame");
  function probe() {{
    var doc = frame.contentDocument;
    var charts = doc.querySelectorAll("svg.chart");
    var smallest = Infinity;
    for (var i = 0; i < charts.length; i++) {{
      var chart = charts[i];
      var viewBox = chart.viewBox.baseVal.width || 720;
      var scale = chart.getBoundingClientRect().width / viewBox;
      var texts = chart.querySelectorAll("text");
      for (var j = 0; j < texts.length; j++) {{
        var size = parseFloat(window.getComputedStyle(texts[j]).fontSize);
        if (size && scale * size < smallest) smallest = scale * size;
      }}
    }}
    document.title = "type=" + (charts.length ? smallest.toFixed(2) : "none")
      + " charts=" + charts.length;
  }}
  frame.addEventListener("load", probe);
  if (frame.contentDocument && frame.contentDocument.readyState === "complete") probe();
</script>
"""


def probe_chart_type(browser: str, page: Path, width: int) -> tuple[float, int]:
    """`(smallest rendered chart text in px, chart count)` at a `width`-wide frame."""
    wrapper = page.with_name(f"probe-{width}.html")
    wrapper.write_text(_PROBE.format(page=page.name, width=width), encoding="utf-8")
    dumped = subprocess.run(
        [
            browser, "--headless", "--disable-gpu", "--hide-scrollbars",
            "--allow-file-access-from-files",
            "--window-size=1400,900", "--virtual-time-budget=4000",
            "--dump-dom", wrapper.as_uri(),
        ],
        capture_output=True, text=True, timeout=120, check=True,
    ).stdout
    match = re.search(r"<title>type=([\d.]+|none) charts=(\d+)</title>", dumped)
    assert match, "the probe never ran — the frame did not load"
    return float(match.group(1)), int(match.group(2))


def test_the_page_does_not_scroll_sideways_on_a_phone(browser, page):
    scroll, viewport = measure(browser, page, PHONE_WIDTH)

    assert viewport == PHONE_WIDTH, "the frame did not lay out at the width it was given"
    assert scroll <= viewport, (
        f"the page is {scroll}px wide in a {viewport}px viewport: "
        f"{scroll - viewport}px of it is off-screen to the right"
    )


def test_the_page_does_not_scroll_sideways_on_a_desktop_either(browser, page):
    scroll, viewport = measure(browser, page, DESKTOP_WIDTH)

    assert scroll <= viewport


def test_the_page_still_uses_the_width_it_is_given(browser, page):
    """A page that fits by collapsing to one narrow column has not been fixed."""
    _, viewport = measure(browser, page, DESKTOP_WIDTH)

    assert viewport > PHONE_WIDTH, "the page did not lay out wider when given more room"


def test_every_chart_stays_legible_on_a_phone(browser, page):
    """A chart that fits the screen by shrinking its type below reading size is not
    responsive — it is unreadable, which is worse than a scroll.

    Nine pixels is the floor: the smallest type a chart carries is its 11px axis
    numbers, so the chart may scale down to about 0.8 and no further. At phone width
    that means the chart keeps a minimum width and its own card scrolls it, which the
    page body never does.
    """
    smallest, charts = probe_chart_type(browser, page, PHONE_WIDTH)

    assert charts >= 3, "the probe found no charts to measure"
    assert smallest >= 9.0, (
        f"the smallest chart text renders at {smallest}px on a {PHONE_WIDTH}px screen"
    )


def test_the_charts_take_the_room_a_desktop_gives_them(browser, page):
    """The floor is for phones. On a desktop the chart fills its card, not 620px."""
    smallest, _ = probe_chart_type(browser, page, DESKTOP_WIDTH)

    assert smallest >= 11.0, "a chart should render its type at full size when there is room"
