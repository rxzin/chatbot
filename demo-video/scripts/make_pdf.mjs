// A short, clearly fictional handbook for the demo, printed to PDF with Chromium.
import { chromium } from "playwright";

const html = `<!doctype html><html><head><meta charset="utf-8"><style>
  body { font: 12pt/1.6 Georgia, serif; color: #111; margin: 0; }
  .page { padding: 64px 72px; page-break-after: always; }
  .page:last-child { page-break-after: auto; }
  h1 { font: 600 22pt/1.2 Helvetica, Arial, sans-serif; margin: 0 0 4px; }
  h2 { font: 600 14pt/1.3 Helvetica, Arial, sans-serif; margin: 28px 0 6px; }
  .note { font: 10pt Helvetica, Arial, sans-serif; color: #666; margin-bottom: 28px; }
</style></head><body>
<div class="page">
  <h1>Northwind Studio: Team Handbook</h1>
  <p class="note">A fictional sample document made for a product demo. Northwind Studio is not a real company.</p>
  <h2>1. Working hours</h2>
  <p>Our core hours are 10:00 to 16:00 in your local time zone. Outside core hours you can arrange your day as you like, as long as you work 38 hours a week.</p>
  <h2>2. Remote work</h2>
  <p>Everyone can work remotely up to three days a week. Thursdays are studio days, when the whole team works from the office for planning and reviews.</p>
  <p>If you want to work fully remotely for more than two weeks, ask your team lead at least ten working days in advance.</p>
  <h2>3. Equipment</h2>
  <p>Each new starter receives a laptop and a one-off home office budget of 600 euros for a desk, chair or monitor. Receipts go to finance within 30 days.</p>
</div>
<div class="page">
  <h2>4. Time off</h2>
  <p>Full-time staff get 27 days of paid leave a year, plus public holidays. Up to five unused days can be carried over to the next year, and must be used by the end of March.</p>
  <p>Book leave of more than a week at least four weeks ahead, so projects can be planned around it.</p>
  <h2>5. Learning</h2>
  <p>Each person has a yearly learning budget of 1,200 euros for courses, books and conferences, and two learning days to use as they choose.</p>
  <h2>6. Who to ask</h2>
  <p>For questions about pay or leave, contact the people team. For laptops and accounts, contact the IT desk. In an emergency outside office hours, call the duty manager.</p>
</div>
</body></html>`;

const b = await chromium.launch();
const p = await b.newPage();
await p.setContent(html);
await p.pdf({ path: process.argv[2], format: "A4", printBackground: true });
await b.close();
console.log("pdf written");
