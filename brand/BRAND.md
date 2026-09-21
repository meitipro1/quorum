# Brand

A small, fixed set of assets. Everything is SVG except the social card, which
GitHub needs as a raster.

| File | What it is | Where it goes |
|---|---|---|
| [`mark.svg`](mark.svg) | The mark alone, 100 x 100 | favicon, avatar, anything under 200px |
| [`lockup.svg`](lockup.svg) | Mark plus wordmark | README header, slides, docs |
| [`social.svg`](social.svg) | 1280 x 640 source | edit this, then re-export |
| [`social.png`](social.png) | 1280 x 640 export | Settings -> General -> Social preview |

## The mark

Three strokes from three separate points, meeting at one, above a chalk line.

The strokes are the sources. They start apart because they are independent -
each belongs to the account that submitted it, and nobody, the registrar
included, can move another's. They meet because a fact here is established only
where enough of them land on the same answer. The chalk line beneath is the
record the reading is written to. A mark showing a tick would be describing an
answer; this describes the condition for having one, and the condition is the
whole primitive.

Built on a 100 x 100 grid. Stroke weight 8, round caps and joins, corner radius
18. The record is chalk at 4, thinner than the sources and in a different
colour, so it reads as the ground rather than as a fourth source.

- **Clear space:** half the mark height on every side.
- **Smallest size:** 18px alone, 24px locked to the wordmark. Verified - the
  three strokes stay separable at the top and the meeting point stays a point.
- **Never:** a second hue, a gradient, an outline version, a drop shadow, or the
  mark flipped. Flipped, one point fans out into three, which is the opposite
  of what happens.

## Palette

| Token | Hex | Use |
|---|---|---|
| ink | `#0C0D10` | the mark's field, any dark surface |
| chalk | `#E8E6E1` | the wordmark, primary text, the record. Never pure white |
| accent | `#5B8DEF` | the mark, one primary action, one live state |
| muted | `#9AA0A8` | secondary text |
| rule | `#232830` | hairlines and dividers |

One accent, used sparingly. On the social card it appears exactly three times:
the top bar, the mark, and the footer line.

The accent is distinct from its siblings on purpose: Crosscheck is violet
`#8B7CF6`, Tolerance green `#3DD68C`, Recant coral `#E0645C`, Ratchet amber
`#E0A23C`, Keystone cyan `#3DBFD6`, Accrue chartreuse `#A8D24A`, Assent magenta `#C567D4`, Covenant
rose `#E86A92`, and this one blue `#5B8DEF`. Same grid, same stroke language, same lockup geometry,
different hue - so the set reads as one hand without reading as one product.

## Type

**Inter**, weights 400 and 700, tracking tightened to -1.4 on the wordmark and
-2.6 at display size. Monospace for anything that is a value rather than a
sentence: `ui-monospace, SFMono-Regular, Menlo, monospace`. The wordmark is
always lowercase.

## Re-exporting the social card

```bash
pip install cairosvg
python -c "import cairosvg; cairosvg.svg2png(url='brand/social.svg', write_to='brand/social.png', output_width=1280, output_height=640)"
```

The native cairo backend is not installed on every machine. Where it is
missing, open `social.svg` in a browser, draw it onto a 1280 x 640 canvas, and
save the canvas as PNG - that is how the card here was made on a machine
without cairo.

Upload under **Settings -> General -> Social preview**. GitHub uses it whenever
a link to this repository is shared.

## Licence

MIT along with the rest of the repository. The name and mark identify this
specific primitive, so if you fork it and change what it does, change the name
too.
