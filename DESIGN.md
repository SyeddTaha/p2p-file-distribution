# Local P2P console design system

Students use this console on a laptop in a lit classroom while explaining a
transfer to an instructor. A light interface keeps tables and verification
details readable alongside terminal windows.

## Colors

Restrained palette, with one green accent for actions and selection. CSS tokens:
`--background: #f6f7f6`, `--surface: #ffffff`, `--text: #202522`,
`--muted: #59635d`, `--border: #d7ddd9`, `--accent: #21633f`,
`--hover: #edf2ee`, `--error: #a12622`. Error color conveys failures only.

## Typography

System UI sans-serif, 16px body, 14px labels and table text, 20px section headings,
25px page headings. Monospace for addresses and hashes; wrap long identifiers.
Use tabular numerals for measurements. No remote font or icon requests.

## Spacing and layout

4px base scale: 4, 8, 12, 16, 24, 32px. A compact top navigation and a centered
1200px working area. Forms use two columns on wide screens and one on mobile.
Tables scroll horizontally within their region. No shadows or decorative motion.

## Components

- Buttons: 4px radius, 1px border, 36px minimum height. Green primary actions,
  neutral secondary actions; visible focus outline and disabled state.
- Inputs: labeled, white, 1px border, consistent padding; help text beside units.
- Tables: left-aligned labels, subtle row separators, numeric columns right aligned.
- Progress: native progress element with green fill and verified byte/chunk text.
- Status: plain text, green for verified/online, red for failed, gray for pending,
  stopped, or disconnected. Labels always carry the meaning.
- Feedback: persistent inline error and loading text; explicit useful empty states.
