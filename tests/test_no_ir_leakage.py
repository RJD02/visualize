from src import schemas


def test_image_response_no_ir_field():
    # Ensure public ImageResponse schema does not expose raw IR
    img_fields = set(schemas.ImageResponse.__fields__.keys()) if hasattr(schemas.ImageResponse, '__fields__') else set(dir(schemas.ImageResponse))
    assert 'svg_text' not in img_fields
    assert 'ir' not in img_fields and 'ir_json' not in img_fields
