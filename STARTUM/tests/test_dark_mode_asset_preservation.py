from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_original_dark_mode_hero_image_is_byte_identical():
    image = ROOT / "frontend/assets/images/startum-aeline-student.jpg"
    assert image.is_file()
    assert sha256(image.read_bytes()).hexdigest() == (
        "fbb43b62abaf5f393c82172e1ad29e9eeef2adc7d7aaf52b8d4652474d4832b5"
    )


def test_dark_mode_theme_uses_new_generated_hero_and_preserves_original():
    script = (ROOT / "frontend/script.js").read_text(encoding="utf-8")
    assert '"assets/images/startum-dark-hero.webp"' in script
    original = ROOT / "frontend/assets/images/startum-aeline-student.jpg"
    assert original.is_file()
    assert sha256(original.read_bytes()).hexdigest() == (
        "fbb43b62abaf5f393c82172e1ad29e9eeef2adc7d7aaf52b8d4652474d4832b5"
    )


def test_german_teacher_image_is_available_and_used_by_the_profile():
    image = ROOT / "frontend/assets/images/nemis-tili-ustoz.png"
    assert image.is_file()
    script = (ROOT / "frontend/script.js").read_text(encoding="utf-8")
    assert 'img: "assets/images/nemis-tili-ustoz.png"' in script
    assert '"komil nomozov"' in script
