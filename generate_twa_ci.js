'use strict';
// CI-friendly TWA project generator (non-interactive, Linux-compatible)
// Uses auto-discovery of bubblewrap module paths (no hardcoded paths)
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

function findBubblewrapModule(moduleName) {
  try {
    // Try to resolve from global node_modules
    const globalRoot = execSync('npm root -g', { encoding: 'utf8' }).trim();
    const modulePath = path.join(globalRoot, moduleName);
    if (fs.existsSync(modulePath)) return modulePath;

    // Try nested in @bubblewrap/cli
    const cliPath = path.join(globalRoot, '@bubblewrap', 'cli');
    if (fs.existsSync(cliPath)) {
      const nestedPath = path.join(cliPath, 'node_modules', moduleName);
      if (fs.existsSync(nestedPath)) return nestedPath;
    }

    // Try require.resolve as last resort
    return require.resolve(moduleName);
  } catch (e) {
    console.error('Cannot find module:', moduleName);
    console.error('Global npm root:', execSync('npm root -g', { encoding: 'utf8' }).trim());
    throw e;
  }
}

async function main() {
  const projectDir = path.resolve(process.cwd(), 'twa-project');
  const twaConfig = JSON.parse(fs.readFileSync('twa-config.json', 'utf8'));

  // Auto-discover bubblewrap paths
  const corePath = findBubblewrapModule('@bubblewrap/core');
  const cliPath = findBubblewrapModule('@bubblewrap/cli');
  const colorPath = findBubblewrapModule('color');

  const core = require(corePath);
  const shared = require(path.join(cliPath, 'dist', 'lib', 'cmds', 'shared'));
  const Color = require(colorPath);

  console.log('Fetching web manifest...');
  const manifestUrl = 'https://trudnik.onrender.com/static/manifest.json';
  let m = await core.TwaManifest.fromWebManifest(manifestUrl);

  console.log('Manifest loaded:', m.name, '| display:', m.display, '| theme:', m.themeColor);

  console.log('Applying config...');
  m.packageId = twaConfig.packageId;
  m.host = twaConfig.host;
  m.name = twaConfig.name;
  m.launcherName = twaConfig.launcherName;
  m.display = twaConfig.display;
  m.themeColor = new Color(twaConfig.themeColor);
  m.backgroundColor = new Color(twaConfig.backgroundColor);
  m.startUrl = twaConfig.startUrl;
  m.navigationColor = new Color(twaConfig.navigationColor);
  m.navigationColorDark = new Color(twaConfig.navigationColorDark);
  m.navigationDividerColor = new Color(twaConfig.navigationDividerColor);
  m.navigationDividerColorDark = new Color(twaConfig.navigationDividerColorDark);
  m.splashScreenFadeOutDuration = twaConfig.splashScreenFadeOutDuration;
  m.fallbackType = twaConfig.fallbackType;
  m.enableNotifications = twaConfig.enableNotifications;

  const baseUrl = 'https://trudnik.onrender.com';
  m.iconUrl = twaConfig.icon.startsWith('http') ? twaConfig.icon : baseUrl + '/' + twaConfig.icon.replace(/^\//, '');
  m.maskableIconUrl = twaConfig.maskableIcon.startsWith('http') ? twaConfig.maskableIcon : baseUrl + '/' + twaConfig.maskableIcon.replace(/^\//, '');
  m.monochromeIconUrl = twaConfig.monochromeIcon.startsWith('http') ? twaConfig.monochromeIcon : baseUrl + '/' + twaConfig.monochromeIcon.replace(/^\//, '');

  m.signingKey = { path: twaConfig.signingKey.path, alias: twaConfig.signingKey.alias };
  if (twaConfig.features) m.features = twaConfig.features;
  if (twaConfig.alphaDependencies) m.alphaDependencies = twaConfig.alphaDependencies;

  if (!fs.existsSync(projectDir)) fs.mkdirSync(projectDir, { recursive: true });

  const manifestPath = path.join(projectDir, 'twa-manifest.json');
  await m.saveToFile(manifestPath);

  const gen = new core.TwaGenerator();
  const mp = {
    printMessage: () => {},
    promptConfirm: async (_, d) => d,
    promptInput: async (_, d) => d,
    promptChoice: async (_, __, d) => d,
    promptPassword: async () => 'x',
    promptRawList: async (_, __, d) => d
  };
  await shared.generateTwaProject(mp, gen, projectDir, m);
  await shared.generateManifestChecksumFile(manifestPath, projectDir);

  const ks = 'trudnik-release.keystore';
  if (fs.existsSync(ks)) fs.copyFileSync(ks, path.join(projectDir, ks));

  console.log('TWA project generated successfully');
}

main().catch(e => {
  console.error('FATAL:', e.message);
  console.error(e.stack);
  process.exit(1);
});
