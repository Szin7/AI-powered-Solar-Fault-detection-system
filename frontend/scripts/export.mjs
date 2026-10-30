import { cp, mkdir, readFile, writeFile, readdir, rm } from 'node:fs/promises'
import { resolve, join } from 'node:path'
import { createHash } from 'node:crypto'

const output = resolve('out')
const target = resolve('../src/solarsense/static')
// External scripts let the exported dashboard keep script-src 'self'.
async function externalize(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) await externalize(path)
    else if (entry.name.endsWith('.html')) {
      let html = await readFile(path, 'utf8')
      const scripts = [...html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)]
      for (const match of scripts) {
        if (/\bsrc=/.test(match[1]) || !match[2].trim()) continue
        const name = 'bootstrap-' + createHash('sha256').update(match[2]).digest('hex').slice(0, 16) + '.js'
        await writeFile(join(output, name), match[2])
        html = html.replace(match[0], `<script${match[1]} src="/${name}"></script>`)
      }
      await writeFile(path, html)
    }
  }
}
await externalize(output)
// Keep the prior operations dashboard available at /operations/.
for (const entry of await readdir(target)) {
  if (entry !== 'operations') await rm(join(target, entry), { recursive: true, force: true })
}
await mkdir(target, { recursive: true })
await cp(output, target, { recursive: true })
console.log('Exported original dashboard to ' + target)
