export default function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', '*');
  
  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }
  
  return res.status(200).json({
    ok: true,
    platform: "vercel",
    cli_found: false,
    ffmpeg_found: false,
    cloud_ready: true,
    message: "Vercel Cloud Serverless Ready"
  });
}
