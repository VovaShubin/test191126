#!/usr/bin/env node

'use strict';

const http = require('node:http');
const https = require('node:https');
const { performance } = require('node:perf_hooks');

const REQUEST_COUNT = 10;
const MAX_REDIRECTS = 10;

function download(url, redirectsLeft = MAX_REDIRECTS) {
  return new Promise((resolve, reject) => {
    const client = url.protocol === 'http:' ? http : https;
    const request = client.get(url, {
      headers: {
        'user-agent': 'node-download-speed-test/1.0',
      },
    });

    request.on('response', (response) => {
      const statusCode = response.statusCode ?? 0;
      const location = response.headers.location;

      if (statusCode >= 300 && statusCode < 400 && location) {
        response.resume();

        if (redirectsLeft === 0) {
          reject(new Error('Слишком много перенаправлений'));
          return;
        }

        response.on('end', () => {
          download(new URL(location, url), redirectsLeft - 1)
            .then(resolve, reject);
        });
        return;
      }

      if (statusCode < 200 || statusCode >= 300) {
        response.resume();
        reject(new Error(`Сервер вернул HTTP ${statusCode}`));
        return;
      }

      let bytes = 0;

      response.on('data', (chunk) => {
        bytes += chunk.length;
      });
      response.on('end', () => resolve(bytes));
      response.on('error', reject);
    });

    request.on('error', reject);
  });
}

async function main() {
  const address = process.argv[2];

  if (!address) {
    console.error('Использование: node download-speed.js <URL>');
    process.exitCode = 1;
    return;
  }

  let url;
  try {
    url = new URL(address);
  } catch {
    console.error('Ошибка: укажите корректный URL, включая http:// или https://');
    process.exitCode = 1;
    return;
  }

  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    console.error('Ошибка: поддерживаются только протоколы HTTP и HTTPS');
    process.exitCode = 1;
    return;
  }

  let totalBytes = 0;
  let totalMilliseconds = 0;

  for (let index = 1; index <= REQUEST_COUNT; index += 1) {
    const startedAt = performance.now();
    const bytes = await download(url);
    const elapsed = performance.now() - startedAt;

    totalBytes += bytes;
    totalMilliseconds += elapsed;
    console.log(
      `Запрос ${index}/${REQUEST_COUNT}: ${(elapsed / 1000).toFixed(3)} с, `
      + `${(bytes / 1024 / 1024).toFixed(2)} МиБ`,
    );
  }

  const averageMilliseconds = totalMilliseconds / REQUEST_COUNT;
  const totalMebibytes = totalBytes / 1024 / 1024;
  const speed = totalMebibytes / (totalMilliseconds / 1000);

  console.log('\nРезультат:');
  console.log(`Среднее время запроса: ${(averageMilliseconds / 1000).toFixed(3)} с`);
  console.log(`Всего скачано: ${totalMebibytes.toFixed(2)} МиБ`);
  console.log(`Средняя скорость скачивания: ${speed.toFixed(2)} МиБ/с`);
}

main().catch((error) => {
  console.error(`Ошибка: ${error.message}`);
  process.exitCode = 1;
});
