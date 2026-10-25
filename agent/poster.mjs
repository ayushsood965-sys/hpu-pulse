import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
dotenv.config({ path: path.resolve(__dirname, '../.env') });

const accessToken = process.env.INSTAGRAM_ACCESS_TOKEN;
const accountId = process.env.INSTAGRAM_ACCOUNT_ID;

if (!accessToken || !accountId) {
  console.error(JSON.stringify({ error: "Missing INSTAGRAM_ACCESS_TOKEN or INSTAGRAM_ACCOUNT_ID in .env" }));
  process.exit(1);
}

const baseUrl = `https://graph.facebook.com/v21.0`;

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function publishSingleImage(imageUrl, caption) {
  const createUrl = `${baseUrl}/${accountId}/media?image_url=${encodeURIComponent(imageUrl)}&caption=${encodeURIComponent(caption)}&access_token=${accessToken}`;
  const createRes = await fetch(createUrl, { method: 'POST' });
  const createData = await createRes.json();

  if (createData.error) {
    throw new Error(createData.error.message || JSON.stringify(createData.error));
  }

  const containerId = createData.id;

  for (let attempt = 0; attempt < 12; attempt++) {
    await sleep(2500);
    const statusUrl = `${baseUrl}/${containerId}?fields=status_code&access_token=${accessToken}`;
    const statusRes = await fetch(statusUrl);
    const statusData = await statusRes.json();

    if (statusData.status_code === 'FINISHED' || !statusData.status_code) {
      break;
    } else if (statusData.status_code === 'ERROR') {
      throw new Error(`Media processing error: ${JSON.stringify(statusData)}`);
    }
  }

  const pubUrl = `${baseUrl}/${accountId}/media_publish?creation_id=${containerId}&access_token=${accessToken}`;
  const pubRes = await fetch(pubUrl, { method: 'POST' });
  const pubData = await pubRes.json();

  if (pubData.error) {
    throw new Error(pubData.error.message || JSON.stringify(pubData.error));
  }

  return pubData.id;
}

async function publishCarousel(imageUrls, caption) {
  if (!imageUrls || imageUrls.length < 2) {
    throw new Error("Carousel requires at least 2 images");
  }

  const childIds = [];
  for (const url of imageUrls) {
    const childUrl = `${baseUrl}/${accountId}/media?image_url=${encodeURIComponent(url)}&is_carousel_item=true&access_token=${accessToken}`;
    const childRes = await fetch(childUrl, { method: 'POST' });
    const childData = await childRes.json();
    if (childData.error) {
      throw new Error(`Child container error: ${childData.error.message}`);
    }
    childIds.push(childData.id);
    await sleep(1500);
  }

  const parentUrl = `${baseUrl}/${accountId}/media?media_type=CAROUSEL&children=${childIds.join(',')}&caption=${encodeURIComponent(caption)}&access_token=${accessToken}`;
  const parentRes = await fetch(parentUrl, { method: 'POST' });
  const parentData = await parentRes.json();

  if (parentData.error) {
    throw new Error(`Parent carousel container error: ${parentData.error.message}`);
  }

  const containerId = parentData.id;

  for (let attempt = 0; attempt < 12; attempt++) {
    await sleep(3000);
    const statusUrl = `${baseUrl}/${containerId}?fields=status_code&access_token=${accessToken}`;
    const statusRes = await fetch(statusUrl);
    const statusData = await statusRes.json();

    if (statusData.status_code === 'FINISHED' || !statusData.status_code) {
      break;
    } else if (statusData.status_code === 'ERROR') {
      throw new Error(`Carousel processing error: ${JSON.stringify(statusData)}`);
    }
  }

  const pubUrl = `${baseUrl}/${accountId}/media_publish?creation_id=${containerId}&access_token=${accessToken}`;
  const pubRes = await fetch(pubUrl, { method: 'POST' });
  const pubData = await pubRes.json();

  if (pubData.error) {
    throw new Error(`Publish carousel error: ${pubData.error.message}`);
  }

  return pubData.id;
}

async function publishReel(videoUrl, caption, audioName = "") {
  let createUrl = `${baseUrl}/${accountId}/media?media_type=REELS&video_url=${encodeURIComponent(videoUrl)}&caption=${encodeURIComponent(caption)}&share_to_feed=true&access_token=${accessToken}`;
  if (audioName && audioName.trim()) {
    createUrl += `&audio_name=${encodeURIComponent(audioName.trim())}`;
  }
  const createRes = await fetch(createUrl, { method: 'POST' });
  const createData = await createRes.json();

  if (createData.error) {
    throw new Error(createData.error.message || JSON.stringify(createData.error));
  }

  const containerId = createData.id;

  // Poll video container status (reels take 10-25 seconds to process)
  for (let attempt = 0; attempt < 18; attempt++) {
    await sleep(3500);
    const statusUrl = `${baseUrl}/${containerId}?fields=status_code&access_token=${accessToken}`;
    const statusRes = await fetch(statusUrl);
    const statusData = await statusRes.json();

    if (statusData.status_code === 'FINISHED') {
      break;
    } else if (statusData.status_code === 'ERROR') {
      throw new Error(`Reel video processing error: ${JSON.stringify(statusData)}`);
    }
  }

  const pubUrl = `${baseUrl}/${accountId}/media_publish?creation_id=${containerId}&access_token=${accessToken}`;
  const pubRes = await fetch(pubUrl, { method: 'POST' });
  const pubData = await pubRes.json();

  if (pubData.error) {
    throw new Error(pubData.error.message || JSON.stringify(pubData.error));
  }

  return pubData.id;
}

async function postComment(mediaId, commentText) {
  const url = `${baseUrl}/${mediaId}/comments`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `message=${encodeURIComponent(commentText)}&access_token=${accessToken}`
  });
  const data = await res.json();
  if (data.error) {
    throw new Error(data.error.message);
  }
  return data.id;
}

async function main() {
  const mode = process.argv[2];

  try {
    let resultId;
    if (mode === '--carousel') {
      const urls = JSON.parse(process.argv[3]);
      const caption = process.argv[4] || "";
      resultId = await publishCarousel(urls, caption);
    } else if (mode === '--reel') {
      const videoUrl = process.argv[3];
      const caption = process.argv[4] || "";
      const audioName = process.argv[5] || "";
      resultId = await publishReel(videoUrl, caption, audioName);
    } else if (mode === '--comment') {
      const mediaId = process.argv[3];
      const text = process.argv[4];
      resultId = await postComment(mediaId, text);
    } else {
      const imageUrl = process.argv[2];
      const caption = process.argv[3] || "";
      resultId = await publishSingleImage(imageUrl, caption);
    }
    console.log(JSON.stringify({ success: true, media_id: resultId }));
  } catch (err) {
    console.error(JSON.stringify({ error: err.message }));
    process.exit(1);
  }
}

main();
