// Keep the approved raster artwork unchanged; SVG viewports remove its empty margins.
const fs = require('node:fs')
const path = require('node:path')
const root = path.resolve(__dirname, '..')
const source = fs.readFileSync(path.join(root, 'design/brand/agriscan-logo-v1.png')).toString('base64')
const svg = viewBox => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}"><image width="1774" height="887" href="data:image/png;base64,${source}"/></svg>\n`
for (const app of ['frontend', 'mobile']) {
  const destination = path.join(root, app, 'public', 'brand')
  fs.mkdirSync(destination, {recursive: true})
  fs.writeFileSync(path.join(destination, 'logo.svg'), svg('155 195 1480 535'))
  fs.writeFileSync(path.join(destination, 'icon.svg'), svg('145 75 760 760'))
}
