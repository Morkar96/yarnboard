/**
 * Static Terms of Use text, in both of the site's two languages -- shown
 * per the current UI language (see NavBar's toggle), not routed through
 * i18next's en.json/he.json like the rest of the app's UI chrome: this
 * is one long, legally-exact document per language, not a set of short
 * interpolated strings, so keeping it as plain JSX here avoids bloating
 * those files with paragraphs of legal text. Content supplied directly
 * by the site operator -- preserved verbatim, not paraphrased.
 */
import { useTranslation } from "react-i18next";
import { isRtl } from "../i18n";

const CONTACT_EMAIL = "moredolls54@gmail.com";

function MailLink() {
  return <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>;
}

function TermsHebrew() {
  return (
    <>
      <h1 className="mb-1">תקנון שימוש – Yarnboard</h1>
      <p className="text-muted mb-4">9 באוקטובר 2026 · @Mor Karniely</p>

      <h2 className="h4 mt-4">1. כללי</h2>
      <p>
        1.1. ברוכים הבאים ל-Yarnboard (להלן: "האתר"), בכתובת www.yarnboard.net. האתר מופעל על
        ידי מור קרניאלי (להלן: "המפעילה" או "אנחנו").
      </p>
      <p>
        1.2. השימוש באתר, לרבות גלישה, הרשמה והעלאת תוכן, מהווה הסכמה לתנאי תקנון זה ולמדיניות
        הפרטיות של האתר. אם אינך מסכים/ה לתנאים, אנא הימנע/י משימוש באתר.
      </p>
      <p>1.3. התקנון כתוב בלשון זכר מטעמי נוחות בלבד, והוא מתייחס לכל המגדרים באופן שווה.</p>
      <p>1.4. כותרות הסעיפים נועדו לנוחות הקריאה בלבד ואין לפרש את התקנון לפיהן.</p>

      <h2 className="h4 mt-4">2. הגדרות</h2>
      <ul>
        <li>
          "השירות" – כל השירותים והכלים שהאתר מציע, לרבות העלאת דוגמיות, שמירתן וניהול מעקב אחר
          התקדמות בעבודה.
        </li>
        <li>"משתמש" – כל אדם הגולש באתר או משתמש בשירות, בין אם נרשם ובין אם לאו.</li>
        <li>
          "דוגמית" – הוראות סריגה, סריגה בקרושה או מלאכת יד אחרת, בכל פורמט: קישור, דף HTML, קובץ
          PDF, תרשים Stitch Fiddle וכדומה.
        </li>
        <li>
          "תוכן משתמש" – כל תוכן שמשתמש מעלה, מקשר או מזין לאתר, לרבות דוגמיות, תמונות, הערות
          ונתוני התקדמות.
        </li>
      </ul>

      <h2 className="h4 mt-4">3. השירות</h2>
      <p>
        3.1. האתר מאפשר למשתמשים להעלות דוגמיות לשימושם האישי, לשמור אותן במקום אחד ולעקוב אחר
        ההתקדמות בעבודה, למשל לפי שורות או חלקים.
      </p>
      <p>
        3.2. השירות ניתן כיום ללא תשלום. המפעילה רשאית בעתיד להוסיף שירותים בתשלום, ותודיע על כך
        מראש.
      </p>
      <p>
        3.3. השירות ניתן כמות שהוא (AS IS) וכפי שהוא זמין (AS AVAILABLE). המפעילה רשאית לשנות,
        להוסיף או להסיר תכונות בכל עת.
      </p>
      <p>
        3.4. המפעילה אינה מתחייבת שהשירות יפעל ללא הפסקות או תקלות. מומלץ לשמור עותק נפרד של
        דוגמיות חשובות ושל נתוני התקדמות.
      </p>

      <h2 className="h4 mt-4">4. הרשמה וחשבון משתמש</h2>
      <p>4.1. חלק מהשירותים מחייבים הרשמה ופתיחת חשבון. בעת ההרשמה יש למסור פרטים נכונים ומלאים.</p>
      <p>
        4.2. השימוש באתר מותר למי שמלאו לו 18 שנים. הורה או אפוטרופוס רשאי לפתוח חשבון עבור ילדו
        שטרם מלאו לו 18. במקרה כזה עליו לשלוח הודעה על כך לכתובת <MailLink />, והוא יהיה אחראי
        לשימוש שנעשה בחשבון ולמידע שנמסר בו.
      </p>
      <p>
        4.3. המשתמש אחראי לשמור על סודיות פרטי הכניסה לחשבונו ולכל פעולה שנעשית בו. יש להודיע
        למפעילה מיד על כל שימוש לא מורשה בחשבון.
      </p>
      <p>4.4. חשבון הוא אישי ואין להעבירו לאחר.</p>

      <h2 className="h4 mt-4">5. תוכן משתמש וזכויות יוצרים</h2>
      <p>
        5.1. דוגמיות סריגה הן יצירות המוגנות בזכויות יוצרים של המעצבים שיצרו אותן. העלאת דוגמית
        לאתר אינה מעניקה למשתמש או למפעילה זכויות בה.
      </p>
      <p>
        5.2. המשתמש מצהיר שיש לו זכות להעלות כל תוכן שהוא מעלה. למשל: הוא יצר אותו בעצמו, רכש אותו
        כדין לשימושו האישי, או שהדוגמית הוצעה בחינם על ידי בעל הזכויות.
      </p>
      <p>
        5.3. דוגמית שנרכשה בתשלום מיועדת לשימוש האישי של הרוכש בלבד. אין לשתף אותה עם משתמשים
        אחרים דרך האתר, ואין להעלותה באופן שיהפוך אותה לנגישה לציבור.
      </p>
      <p>5.4. האחריות לתוכן משתמש חלה על המשתמש שהעלה אותו בלבד. המפעילה אינה בודקת מראש את התוכן המועלה.</p>
      <p>
        5.5. הזכויות בתוכן המשתמש נשארות אצל בעליהן. המשתמש מעניק למפעילה רישיון מוגבל, לא בלעדי
        וללא תמורה לאחסן, להציג ולעבד את התוכן, אך ורק לצורך מתן השירות לאותו משתמש.
      </p>
      <p>5.6. מומלץ לשמור בכל דוגמית קישור למקור ואת שם המעצב, כאות כבוד ליוצרים.</p>

      <h2 className="h4 mt-4">6. שימושים אסורים</h2>
      <p>אין להשתמש באתר כדי:</p>
      <ul>
        <li>להעלות, לשתף או להפיץ דוגמיות או תכנים שאין למשתמש זכות בהם.</li>
        <li>להעלות תוכן פוגעני, מאיים, מטעה, בלתי חוקי או מפר פרטיות של אחר.</li>
        <li>להעלות קבצים המכילים וירוסים, קוד זדוני או רכיבים שעלולים לפגוע באתר או במשתמשים.</li>
        <li>לנסות לחדור לחשבונות של אחרים, למערכות האתר או לנתונים שאינם שלך.</li>
        <li>לאסוף מידע מהאתר באופן אוטומטי (סריקה, scraping) ללא אישור מראש ובכתב.</li>
        <li>להעמיס על האתר או לשבש את פעילותו התקינה.</li>
        <li>לעשות שימוש מסחרי בשירות ללא אישור המפעילה.</li>
      </ul>

      <h2 className="h4 mt-4">7. קניין רוחני של האתר</h2>
      <p>
        7.1. כל הזכויות באתר עצמו, לרבות העיצוב, הקוד, הסימן Yarnboard, הלוגו והטקסטים שכתבה
        המפעילה, שייכות למפעילה.
      </p>
      <p>
        7.2. אין להעתיק, לשכפל, להפיץ או לעשות שימוש מסחרי ברכיבים אלה ללא אישור מראש ובכתב
        מהמפעילה.
      </p>
      <p>7.3. האמור בסעיף זה אינו חל על תוכן משתמש, שהזכויות בו נשארות אצל בעליו כאמור בסעיף 5.</p>

      <h2 className="h4 mt-4">8. פרטיות</h2>
      <p>
        8.1. המפעילה אוספת את המידע הנדרש להפעלת השירות בלבד, כגון כתובת דוא"ל, שם משתמש, הדוגמיות
        שהועלו ונתוני ההתקדמות.
      </p>
      <p>
        8.2. המידע נשמר במאגרי מידע מאובטחים, ואינו נמכר או מועבר לצדדים שלישיים, למעט ספקי שירות
        הדרושים להפעלת האתר (כגון אחסון) או כנדרש על פי דין.
      </p>
      <p>8.3. הפרטים המלאים מופיעים במדיניות הפרטיות של האתר, המהווה חלק בלתי נפרד מתקנון זה.</p>

      <h2 className="h4 mt-4">9. הגבלת אחריות</h2>
      <p>9.1. המפעילה אינה אחראית לתוכן הדוגמיות שמשתמשים מעלים, לדיוקן או לתוצאות השימוש בהן.</p>
      <p>
        9.2. המפעילה אינה אחראית לאובדן מידע, לרבות דוגמיות או נתוני התקדמות, שנגרם עקב תקלה,
        הפסקת שירות או כל סיבה אחרת.
      </p>
      <p>9.3. קישורים לאתרים חיצוניים מופיעים לנוחות המשתמשים בלבד. המפעילה אינה אחראית לתוכנם או לזמינותם.</p>
      <p>
        9.4. המשתמש ישפה את המפעילה בגין כל נזק או הוצאה שייגרמו לה עקב הפרת תקנון זה על ידו,
        לרבות תביעה בגין הפרת זכויות יוצרים בתוכן שהעלה.
      </p>

      <h2 className="h4 mt-4">10. הודעה על הפרת זכויות והסרת תוכן</h2>
      <p>
        10.1. בעל זכויות הסבור שתוכן באתר מפר את זכויותיו מוזמן לפנות אל <MailLink /> ולציין:
      </p>
      <ol>
        <li>פרטי התקשרות.</li>
        <li>תיאור היצירה המוגנת והוכחה לבעלות עליה.</li>
        <li>מיקום התוכן המפר באתר.</li>
        <li>הצהרה שהמידע בפנייה נכון.</li>
      </ol>
      <p>
        10.2. המפעילה תבחן כל פנייה בהקדם, ורשאית להסיר או לחסום תוכן לפי שיקול דעתה, וכן להודיע
        על כך למשתמש שהעלה אותו.
      </p>
      <p>10.3. המפעילה רשאית להסיר כל תוכן שלדעתה מפר את התקנון, גם ללא פנייה מוקדמת.</p>

      <h2 className="h4 mt-4">11. הפסקת שירות וסגירת חשבון</h2>
      <p>
        11.1. המשתמש רשאי לסגור את חשבונו בכל עת. עם סגירת החשבון יימחקו הדוגמיות ונתוני
        ההתקדמות שלו תוך זמן סביר, למעט מידע שיש חובה לשמור על פי דין.
      </p>
      <p>11.2. המפעילה רשאית להשעות או לסגור חשבון של משתמש שהפר את התקנון, לאחר הודעה מראש ככל שהדבר אפשרי.</p>
      <p>
        11.3. המפעילה רשאית להפסיק את פעילות האתר כולו. במקרה כזה תינתן הודעה של 30 ימים לפחות,
        כדי לאפשר למשתמשים לשמור את התוכן שלהם.
      </p>

      <h2 className="h4 mt-4">12. שינויים, דין וסמכות שיפוט ויצירת קשר</h2>
      <p>
        12.1. המפעילה רשאית לעדכן תקנון זה מעת לעת. שינוי מהותי יפורסם באתר או יישלח בדוא"ל לפחות
        14 ימים לפני כניסתו לתוקף. המשך השימוש באתר לאחר מכן מהווה הסכמה לנוסח המעודכן.
      </p>
      <p>
        12.2. על תקנון זה יחולו דיני מדינת ישראל בלבד. סמכות השיפוט הבלעדית בכל עניין הנוגע לאתר
        נתונה לבתי המשפט המוסמכים במחוז תל אביב-יפו.
      </p>
      <p>
        12.3. לשאלות, הערות או פניות בנוגע לתקנון ניתן לפנות אל: <MailLink />.
      </p>

      <p className="text-muted mt-4">עודכן לאחרונה: 09.10.2026</p>
    </>
  );
}

function TermsEnglish() {
  return (
    <>
      <h1 className="mb-1">Yarnboard – Terms of Use</h1>
      <p className="text-muted mb-4">Last updated: 9 October 2026</p>

      <h2 className="h4 mt-4">1. General</h2>
      <p>
        1.1. Welcome to Yarnboard (the "Site"), at www.yarnboard.net. The Site is operated by Mor
        Karniali (the "Operator", "we" or "us").
      </p>
      <p>
        1.2. By using the Site, including browsing, registering or uploading content, you agree
        to these Terms of Use and to the Site's Privacy Policy. If you do not agree, please do
        not use the Site.
      </p>
      <p>
        1.3. These Terms are published in Hebrew and English. If the two versions differ, the
        Hebrew version prevails.
      </p>
      <p>1.4. Section headings are for convenience only and do not affect the interpretation of these Terms.</p>

      <h2 className="h4 mt-4">2. Definitions</h2>
      <ul>
        <li>
          "Service" – all services and tools the Site offers, including uploading and saving
          patterns and tracking progress on your work.
        </li>
        <li>"User" – anyone who browses the Site or uses the Service, whether registered or not.</li>
        <li>
          "Pattern" – instructions for knitting, crochet or another craft, in any format: a link,
          an HTML page, a PDF file, a Stitch Fiddle chart and so on.
        </li>
        <li>
          "User Content" – any content a User uploads, links to or enters on the Site, including
          patterns, images, notes and progress data.
        </li>
      </ul>

      <h2 className="h4 mt-4">3. The Service</h2>
      <p>
        3.1. The Site lets Users upload patterns for their personal use, keep them in one place
        and track their progress, for example by row or by part.
      </p>
      <p>
        3.2. The Service is currently free of charge. The Operator may add paid services in the
        future and will give notice in advance.
      </p>
      <p>
        3.3. The Service is provided "as is" and "as available". The Operator may change, add or
        remove features at any time.
      </p>
      <p>
        3.4. The Operator does not guarantee that the Service will run without interruptions or
        errors. We recommend keeping a separate copy of important patterns and progress data.
      </p>

      <h2 className="h4 mt-4">4. Registration and Accounts</h2>
      <p>4.1. Some services require registering and opening an account. You must provide accurate and complete details when registering.</p>
      <p>
        4.2. The Site may be used by people aged 18 or over. A parent or legal guardian may open
        an account on behalf of their child under 18. In that case they must notify us by email
        at <MailLink />, and they are responsible for the use of the account and for the
        information provided in it.
      </p>
      <p>
        4.3. You are responsible for keeping your login details confidential and for all activity
        in your account. Notify the Operator immediately of any unauthorized use of your account.
      </p>
      <p>4.4. Accounts are personal and may not be transferred to anyone else.</p>

      <h2 className="h4 mt-4">5. User Content and Copyright</h2>
      <p>
        5.1. Knitting patterns are works protected by the copyright of the designers who created
        them. Uploading a pattern to the Site does not give the User or the Operator any rights
        in it.
      </p>
      <p>
        5.2. You confirm that you have the right to upload any content you upload. For example:
        you created it yourself, you lawfully purchased it for your personal use, or the rights
        holder offered the pattern for free.
      </p>
      <p>
        5.3. A pattern purchased for a fee is for the purchaser's personal use only. It may not
        be shared with other Users through the Site or uploaded in a way that makes it publicly
        accessible.
      </p>
      <p>5.4. Responsibility for User Content lies solely with the User who uploaded it. The Operator does not review uploaded content in advance.</p>
      <p>
        5.5. Rights in User Content remain with their owners. You grant the Operator a limited,
        non-exclusive, royalty-free licence to store, display and process the content solely to
        provide the Service to you.
      </p>
      <p>5.6. We recommend keeping a link to the source and the designer's name with every pattern, out of respect for its creator.</p>

      <h2 className="h4 mt-4">6. Prohibited Use</h2>
      <p>You may not use the Site to:</p>
      <ul>
        <li>Upload, share or distribute patterns or content you do not have the right to.</li>
        <li>Upload offensive, threatening, misleading or unlawful content, or content that violates another person's privacy.</li>
        <li>Upload files containing viruses, malicious code or anything that could harm the Site or its Users.</li>
        <li>Attempt to access other people's accounts, the Site's systems or data that is not yours.</li>
        <li>Collect data from the Site by automated means (crawling, scraping) without prior written permission.</li>
        <li>Overload the Site or disrupt its normal operation.</li>
        <li>Use the Service commercially without the Operator's permission.</li>
      </ul>

      <h2 className="h4 mt-4">7. Intellectual Property of the Site</h2>
      <p>
        7.1. All rights in the Site itself, including its design, code, the Yarnboard name, logo
        and texts written by the Operator, belong to the Operator.
      </p>
      <p>7.2. These elements may not be copied, reproduced, distributed or used commercially without the Operator's prior written permission.</p>
      <p>7.3. This section does not apply to User Content, which remains with its owners as set out in section 5.</p>

      <h2 className="h4 mt-4">8. Privacy</h2>
      <p>
        8.1. The Operator collects only the information needed to run the Service, such as your
        email address, username, uploaded patterns and progress data.
      </p>
      <p>
        8.2. This information is kept in secure databases and is not sold or passed to third
        parties, except service providers needed to run the Site (such as hosting) or where
        required by law.
      </p>
      <p>8.3. Full details appear in the Site's Privacy Policy, which forms an integral part of these Terms.</p>

      <h2 className="h4 mt-4">9. Limitation of Liability</h2>
      <p>9.1. The Operator is not responsible for the content of patterns Users upload, their accuracy or the results of using them.</p>
      <p>
        9.2. The Operator is not responsible for loss of data, including patterns or progress
        data, caused by a fault, a service interruption or any other reason.
      </p>
      <p>9.3. Links to external websites are provided for convenience only. The Operator is not responsible for their content or availability.</p>
      <p>
        9.4. You will indemnify the Operator for any damage or expense caused by your breach of
        these Terms, including any claim of copyright infringement in content you uploaded.
      </p>

      <h2 className="h4 mt-4">10. Infringement Notices and Content Removal</h2>
      <p>
        10.1. A rights holder who believes content on the Site infringes their rights is welcome
        to write to <MailLink /> and include:
      </p>
      <ol>
        <li>Contact details.</li>
        <li>A description of the protected work and proof of ownership.</li>
        <li>The location of the infringing content on the Site.</li>
        <li>A statement that the information in the notice is accurate.</li>
      </ol>
      <p>10.2. The Operator will review every notice promptly and may remove or block content at its discretion, and inform the User who uploaded it.</p>
      <p>10.3. The Operator may remove any content it believes breaches these Terms, even without prior notice.</p>

      <h2 className="h4 mt-4">11. Suspension and Account Closure</h2>
      <p>
        11.1. You may close your account at any time. When an account is closed, its patterns
        and progress data will be deleted within a reasonable time, except information we are
        required by law to keep.
      </p>
      <p>11.2. The Operator may suspend or close the account of a User who has breached these Terms, with advance notice where possible.</p>
      <p>11.3. The Operator may shut down the Site entirely. If so, at least 30 days' notice will be given so Users can save their content.</p>

      <h2 className="h4 mt-4">12. Changes, Governing Law and Contact</h2>
      <p>
        12.1. The Operator may update these Terms from time to time. A material change will be
        posted on the Site or sent by email at least 14 days before it takes effect. Continuing
        to use the Site after that means you accept the updated Terms.
      </p>
      <p>
        12.2. These Terms are governed solely by the laws of the State of Israel. The competent
        courts in the Tel Aviv-Jaffa district have exclusive jurisdiction over any matter relating
        to the Site.
      </p>
      <p>
        12.3. For questions, comments or requests about these Terms, contact: <MailLink />.
      </p>
    </>
  );
}

export default function TermsPage() {
  const { i18n } = useTranslation();
  const rtl = isRtl(i18n.language);

  return (
    <div dir={rtl ? "rtl" : "ltr"} style={{ maxWidth: "70ch" }}>
      {rtl ? <TermsHebrew /> : <TermsEnglish />}
    </div>
  );
}
