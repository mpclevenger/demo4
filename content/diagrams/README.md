# Diagrams

This folder holds TRAC's diagrams. They are drawn in draw.io, saved here, and shown on the site at `/diagrams/`, on each diagram's own page, and on the Library page of every platform the diagram names.

There are two kinds:

- **Common**: how a kind of platform usually works.
- **Our footprint**: the firm's own setup. These grow as more of it is confirmed.

## What is in this folder

| File | What it is |
|---|---|
| `diagrams.yaml` | The list: one entry per diagram (title, intro, kind, platforms, date checked). |
| `<name>.drawio.svg` | One diagram. It is a picture and also the editable draw.io file. |
| `library/` | The draw.io shape library (the red risk bubble, the blue control bubble, the dashed Proposed bubble and the rest). It is not shown on the site. In draw.io: File > Open Library from > Device, and pick the file. |

## Add a new diagram

1. Open draw.io desktop and open the shape library from `library/` (see above).
2. Draw the diagram. Put a red bubble where something could go wrong and a blue bubble where a control sits.
3. Make each bubble a link (next section).
4. Save it in this folder: File > Save as, and give the file a short name with lowercase letters, digits and dashes that ends in `.drawio.svg`, for example `aws-login-access-flow.drawio.svg`. If draw.io offers a type, pick "Editable Vector Image (.drawio.svg)". Or use File > Export as > SVG and tick **Include a copy of my diagram**, then name the file the same way.
5. Add an entry to `diagrams.yaml`, copying an existing one:

```yaml
diagrams:
  - file: aws-login-access-flow.drawio.svg
    title: AWS login access flow
    intro: One or two plain sentences about what the picture shows.
    kind: footprint            # or common
    platforms: [AWS, Entra ID, Active Directory]   # platform names exactly as TRAC shows them
    as_of: 2026-11-13          # optional: when the facts were last checked
```

6. Run the check: `.\trac.ps1 check` (or `python manage.py check_diagrams`). It says in plain words what to fix.
7. Restart the site (or release it). The diagram appears.

## Update a diagram

1. Open the `.drawio.svg` file in draw.io desktop.
2. Change it, then File > Save. Keep the same file name and the same `.drawio.svg` ending.
3. Change `as_of` in `diagrams.yaml` if you checked the facts again.
4. Run the check, then reload the page: diagrams are read on every page load, so the change shows on the next page load.

## Make a bubble a link

1. Select the bubble.
2. Edit > Edit Link (or right-click > Edit Link).
3. Type the TRAC address:
   - a control: `/rcm/controls/AM-04/`
   - a risk: `/rcm/risks/R-AM-04/`
4. Press Apply.

A red bubble's label is the code without "R-" (it reads AM-04; the red says it's a risk), but its link keeps the "R-" (`/rcm/risks/R-AM-04/`). In the register, give each risk one line on how it could happen here.

The check stops you if the ID isn't in `content/controls`. The page for the diagram lists every control and risk the diagram links to, with their titles.

**Proposed controls:** a control that Tech Risk has written but that isn't in TRAC yet is a **dashed blue bubble with no link**. It shows in the diagram page's "Proposed controls" list by its label. When the control is added to TRAC, give the bubble a solid style and a link.

## Line styles

A solid line means documented or observed. A dashed line means unconfirmed. The page explains this under the picture.

## Good to know

- The site removes anything that could run code from the picture before it shows it. Links must start with `/`, `#`, `https://` or `http://`.
- Big diagrams scroll sideways inside their own box; the page itself doesn't.
- "Download to edit in draw.io" on each page gives the original file back.
- `diagrams.yaml` names platforms exactly as in `content/platforms/catalog.yaml`.
