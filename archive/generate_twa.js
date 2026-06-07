'use strict';

// Программная генерация TWA-проекта через @bubblewrap/core API
const fs = require('fs');
const path = require('path');

const appData = process.env.APPDATA;
const corePath = path.join(appData, 'npm', 'node_modules',
  '@bubblewrap', 'cli', 'node_modules', '@bubblewrap', 'core');
const cliPath = path.join(appData, 'npm', 'node_modules', '@bubblewrap', 'cli');
const colorPath = path.join(appData, 'npm', 'node_modules',
  '@bubblewrap', 'cli', 'node_modules', 'color');

const core = require(corePath);
const shared = require(path.join(cliPath, 'dist', 'lib', 'cmds', 'shared'));
const Color = require(colorPath);

async function main() {
  const projectDir = path.resolve(process.cwd(), 'twa-project');
  const twaConfigPath = path.resolve(process.cwd(), 'twa-config.json');

  console.log('Читаю twa-config.json...');
  const twaConfig = JSON.parse(fs.readFileSync(twaConfigPath, 'utf8'));

  console.log('Загружаю web-манифест...');
  const manifestUrl = 'https://trudnik.onrender.com/static/manifest.json';
  let twaManifest = await core.TwaManifest.fromWebManifest(manifestUrl);

  console.log('Применяю конфигурацию...');
  twaManifest.packageId = twaConfig.packageId;
  twaManifest.host = twaConfig.host;
  twaManifest.name = twaConfig.name;
  twaManifest.launcherName = twaConfig.launcherName;
  twaManifest.display = twaConfig.display;
  twaManifest.themeColor = new Color(twaConfig.themeColor);
  twaManifest.backgroundColor = new Color(twaConfig.backgroundColor);
  twaManifest.startUrl = twaConfig.startUrl;
  twaManifest.navigationColor = new Color(twaConfig.navigationColor);
  twaManifest.navigationColorDark = new Color(twaConfig.navigationColorDark);
  twaManifest.navigationDividerColor = new Color(twaConfig.navigationDividerColor);
  twaManifest.navigationDividerColorDark = new Color(twaConfig.navigationDividerColorDark);
  twaManifest.splashScreenFadeOutDuration = twaConfig.splashScreenFadeOutDuration;
  twaManifest.fallbackType = twaConfig.fallbackType;
  twaManifest.enableNotifications = twaConfig.enableNotifications;

  // Преобразуем относительные пути иконок в полные URL
  const baseUrl = 'https://trudnik.onrender.com';
  twaManifest.iconUrl = twaConfig.icon.startsWith('http') ? twaConfig.icon : baseUrl + '/' + twaConfig.icon.replace(/^\//, '');
  twaManifest.maskableIconUrl = twaConfig.maskableIcon.startsWith('http') ? twaConfig.maskableIcon : baseUrl + '/' + twaConfig.maskableIcon.replace(/^\//, '');
  twaManifest.monochromeIconUrl = twaConfig.monochromeIcon.startsWith('http') ? twaConfig.monochromeIcon : baseUrl + '/' + twaConfig.monochromeIcon.replace(/^\//, '');

  twaManifest.signingKey = {
    path: twaConfig.signingKey.path,
    alias: twaConfig.signingKey.alias,
  };

  if (twaConfig.features) {
    twaManifest.features = twaConfig.features;
  }
  if (twaConfig.alphaDependencies) {
    twaManifest.alphaDependencies = twaConfig.alphaDependencies;
  }

  if (!fs.existsSync(projectDir)) {
    fs.mkdirSync(projectDir, { recursive: true });
  }

  const manifestPath = path.join(projectDir, 'twa-manifest.json');
  console.log('Сохраняю twa-manifest.json...');
  await twaManifest.saveToFile(manifestPath);

  console.log('Генерирую Android-проект...');
  const twaGenerator = new core.TwaGenerator();

  const mockPrompt = {
    printMessage: (msg) => console.log('  ' + (typeof msg === 'string' ? msg : msg())),
    promptConfirm: async (msg, defaultVal) => defaultVal,
    promptInput: async (msg, defaultVal) => defaultVal,
    promptChoice: async (msg, choices, defaultVal) => defaultVal,
    promptPassword: async (msg) => 'password',
    promptRawList: async (msg, choices, defaultVal) => defaultVal,
  };

  await shared.generateTwaProject(mockPrompt, twaGenerator, projectDir, twaManifest);
  await shared.generateManifestChecksumFile(manifestPath, projectDir);

  const keystoreSrc = path.resolve(process.cwd(), 'trudnik-release.keystore');
  const keystoreDst = path.join(projectDir, 'trudnik-release.keystore');
  if (fs.existsSync(keystoreSrc) && !fs.existsSync(keystoreDst)) {
    console.log('Копирую keystore...');
    fs.copyFileSync(keystoreSrc, keystoreDst);
  }

  console.log('\n=== ГОТОВО ===');
  console.log('TWA-проект создан в:', projectDir);
  console.log('Теперь выполни:');
  console.log('  cd twa-project');
  console.log('  bubblewrap build');
}

main().catch(err => {
  console.error('ОШИБКА:', err.message);
  console.error(err.stack);
  process.exit(1);
});
