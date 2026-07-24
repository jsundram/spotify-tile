from geomusic.inputs import id_flags
from geomusic.subdivision import Rect, rect_strip, subdivide_square

SQUARE = Rect(0, 0, 100, 100)


def test_no_flags_four_cells():
    cells = subdivide_square(SQUARE, (False, False, False, False))
    assert len(cells) == 4
    assert all(c.big for c in cells)


def test_published_counts():
    assert len(subdivide_square(SQUARE, id_flags("5ruz"))) == 7
    assert len(subdivide_square(SQUARE, id_flags("76G5"))) == 13
    assert len(subdivide_square(SQUARE, (True, True, False, False))) == 10
    assert len(subdivide_square(SQUARE, (True, True, True, True))) == 16


def test_quadrant_order_matches_quadsub():
    """B1=bottom-left, B2=bottom-right, B3=top-right, B4=top-left."""
    for i, (x, y) in enumerate([(0, 50), (50, 50), (50, 0), (0, 0)]):
        flags = tuple(j == i for j in range(4))
        cells = subdivide_square(SQUARE, flags)
        small = [c for c in cells if not c.big]
        assert len(small) == 4
        assert min(c.rect.x for c in small) == x
        assert min(c.rect.y for c in small) == y


def test_cell_geometry_tiles_the_square():
    cells = subdivide_square(SQUARE, (True, False, True, True))
    assert len(cells) == 13
    area = sum(c.rect.w * c.rect.h for c in cells)
    assert abs(area - 100 * 100) < 1e-6
    for c in cells:
        assert 0 <= c.rect.x < 100 and 0 <= c.rect.y < 100


def test_cell_indices_stable_and_unique():
    cells = subdivide_square(SQUARE, (True, False, False, True))
    assert [c.index for c in cells] == list(range(len(cells)))


def test_rect_strip_heights():
    cells = rect_strip(Rect(0, 0, 100, 300), (1.0, 1.0, 0.5, 0.5))
    assert len(cells) == 4
    assert [round(c.rect.h) for c in cells] == [100, 100, 50, 50]
    assert cells[0].big and cells[1].big
    assert not cells[2].big and not cells[3].big
