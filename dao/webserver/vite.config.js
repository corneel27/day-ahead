import { defaultAllowedOrigins, defineConfig } from 'vite'
import os from 'node:os'

const port = Number(process.env.VITE_DEV_PORT || 5173)

// Hostnames Vite accepts in the Host header, and whose origins may read the
// assets.  Empty by default: IP addresses and localhost are always allowed.
const allowedHosts = (process.env.VITE_DEV_ALLOWED_HOSTS ?? '')
  .split(',')
  .map((hostname) => hostname.trim())
  .filter(Boolean)

// Addresses of this machine the browser could plausibly use.
function localAddresses() {
  const addresses = []
  for (const entries of Object.values(os.networkInterfaces())) {
    for (const entry of entries ?? []) {
      if (entry.family === 'IPv4' && !entry.internal) addresses.push(entry.address)
    }
  }
  return addresses
}

// Origin Vite prefixes to the asset URLs it generates itself: the icon fonts
// referenced from the compiled stylesheets, and anything imported from
// assets/main.js.  It cannot be left unset here.  The page is served by Flask
// on another port, so without an origin Vite emits root relative URLs ("/...")
// which the browser resolves against the Flask origin instead of against the
// dev server, and the fonts 404 - also when everything runs on localhost.
//
// Because it is baked into the config it cannot follow the host the browser
// actually used, so a machine with several reachable addresses (a second NIC, a
// docker bridge, a hostname behind a reverse proxy) may well get the wrong one.
// Pin it in that case:
//   VITE_DEV_ORIGIN=https://dao.example.com   full origin, for a proxy or TLS
//   VITE_DEV_HOST=localhost                   host only, e.g. an SSH tunnel
function devOrigin() {
  if (process.env.VITE_DEV_ORIGIN) {
    return process.env.VITE_DEV_ORIGIN.replace(/\/+$/, '')
  }
  if (process.env.VITE_DEV_HOST) {
    return `http://${process.env.VITE_DEV_HOST}:${port}`
  }
  // A single allowed host is unambiguous: it is the name the browser uses.
  if (allowedHosts.length === 1) {
    return `http://${allowedHosts[0]}:${port}`
  }

  const addresses = localAddresses()
  if (addresses.length === 0) return `http://localhost:${port}`
  if (addresses.length > 1) {
    console.warn(
      `[dao] several addresses found (${addresses.join(', ')}); advertising ` +
      `${addresses[0]} for the generated asset URLs.  Set VITE_DEV_HOST or ` +
      `VITE_DEV_ORIGIN if the browser reaches this machine differently.`
    )
  }
  return `http://${addresses[0]}:${port}`
}

// Origins allowed to fetch the assets.  The page itself is served by Flask on
// another port, so every asset request is cross origin.  Vite only sends the
// CORS headers to localhost by default, which makes the browser discard the
// module and leaves the v2 pages completely unstyled as soon as the browser is
// not on the development machine.  Mirror the allowedHosts rule instead: IP
// addresses and localhost are always accepted, hostnames have to be listed in
// VITE_DEV_ALLOWED_HOSTS.
const ipOrigin = /^https?:\/\/(?:\d{1,3}(?:\.\d{1,3}){3}|\[[0-9a-fA-F:.]+\])(?::\d+)?$/

function hostOrigin(hostname) {
  const escaped = hostname.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(`^https?://${escaped}(?::\\d+)?$`)
}

// defaultAllowedOrigins is a single RegExp (localhost, 127.0.0.1 and [::1]), so
// it is listed as one entry and must not be spread.  Vite matches an array
// entry by entry and recurses into nested arrays, so this keeps working if a
// later version turns it into a list.
const allowedOrigins = [
  defaultAllowedOrigins,
  ipOrigin,
  ...allowedHosts.map(hostOrigin),
]

const origin = devOrigin()

export default defineConfig({
  base: './',
  build: {
    outDir: 'app/static/build',
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: {
        main: 'assets/main.js'
      }
    }
  },
  css: {
    preprocessorOptions: {
      scss: {
        // Bootstrap 5.3 gebruikt intern nog @import en de verouderde
        // globale Sass-functies. Die waarschuwingen kunnen we in onze eigen
        // code niet oplossen, dus onderdrukken we ze voor node_modules.
        // Deprecations in onze eigen .scss blijven wel zichtbaar.
        quietDeps: true,
      },
    },
  },
  server: {
    host: '0.0.0.0',
    port: port,
    strictPort: true,
    origin: origin,
    // Empty by default: localhost and IP addresses are always allowed.
    // Set VITE_DEV_ALLOWED_HOSTS=dao.local,dev.example.com when reaching the
    // server by name or through a reverse proxy.
    allowedHosts: allowedHosts,
    // Without this the browser refuses the assets whenever the application is
    // opened on anything other than localhost; see allowedOrigins above.
    cors: {
      origin: allowedOrigins,
    },
  },
})
