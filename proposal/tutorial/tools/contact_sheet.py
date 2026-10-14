"""Create review contact sheets from saved frames; does not approve any frame."""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageDraw


def main():
    p = argparse.ArgumentParser()
    p.add_argument('source', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('times', nargs='+', type=float)
    args = p.parse_args()
    frames = json.loads((args.source / 'frames.json').read_text('utf8'))
    args.output.mkdir(parents=True, exist_ok=True)
    for offset in range(0, len(args.times), 8):
        items = args.times[offset:offset + 8]
        sheet = Image.new('RGB', (1280, 400 * ((len(items) + 1) // 2)), 'white')
        draw = ImageDraw.Draw(sheet)
        for index, t in enumerate(items):
            f = next(f for f in frames if f['time'] == t)
            im = Image.open(args.source / f['path'])
            im.thumbnail((640, 360))
            x, y = (index % 2) * 640, (index // 2) * 400
            draw.text((x + 10, y + 5), str(t) + 's', fill='black')
            sheet.paste(im, (x, y + 30))
        sheet.save(args.output / (str(offset // 8) + '.jpg'))


if __name__ == '__main__':
    main()
