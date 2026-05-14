import os
import sys
import requests
from bs4 import BeautifulSoup
import re

# تنظات LibGen Mirror (یکی از آینه‌های فعال)
LIBGEN_MIRROR = "http://libgen.is"

def search_libgen(query):
    """جستجو در LibGen و برگرداندن لیست کتاب‌ها"""
    search_url = f"{LIBGEN_MIRROR}/search.php?req={query}&lg_topic=libgen&open=0&view=simple&res=25&phrase=1&column=def"
    response = requests.get(search_url, timeout=30)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # پیدا کردن جدول نتایج
    table = soup.find('table', {'class': 'c'})
    if not table:
        print("هیچ نتیجه‌ای یافت نشد.")
        return []
    
    rows = table.find_all('tr')[1:]  # رد شدن از هدر
    books = []
    for idx, row in enumerate(rows, start=1):
        cols = row.find_all('td')
        if len(cols) < 8:
            continue
        title = cols[2].get_text(strip=True)
        author = cols[1].get_text(strip=True)
        year = cols[4].get_text(strip=True)
        publisher = cols[5].get_text(strip=True)
        # استخراج لینک دانلود (مستقیم از ستون آخر)
        download_link = None
        download_cell = cols[-1]
        link_tag = download_cell.find('a', href=True)
        if link_tag and 'href' in link_tag.attrs:
            download_link = link_tag['href']
        books.append({
            'index': idx,
            'title': title,
            'author': author,
            'year': year,
            'publisher': publisher,
            'download_url': download_link
        })
    return books

def download_book(book, save_path='downloads'):
    """دانلود کتاب و ذخیره آن در مسیر مشخص"""
    if not book['download_url']:
        print("لینک دانلود موجود نیست.")
        return False
    
    # رفع لینک نسبی
    if book['download_url'].startswith('/'):
        download_url = LIBGEN_MIRROR + book['download_url']
    else:
        download_url = book['download_url']
    
    # درخواست دانلود
    response = requests.get(download_url, stream=True, timeout=60)
    if response.status_code != 200:
        print(f"دانلود ناموفق: کد وضعیت {response.status_code}")
        return False
    
    # استخراج نام فایل
    content_disposition = response.headers.get('content-disposition')
    if content_disposition:
        filename = re.findall("filename=(.+)", content_disposition)[0].strip('"')
    else:
        filename = f"{book['title'].replace('/', '_')}.pdf"
    
    os.makedirs(save_path, exist_ok=True)
    filepath = os.path.join(save_path, filename)
    
    with open(filepath, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"کتاب با موفقیت ذخیره شد: {filepath}")
    return True

def main():
    search_term = os.environ.get('SEARCH_TERM')
    book_index_str = os.environ.get('BOOK_INDEX', '').strip()
    
    if not search_term:
        print("لطفاً عبارت جستجو را در input با نام search_term وارد کنید.")
        sys.exit(1)
    
    print(f"در حال جستجوی: {search_term}")
    books = search_libgen(search_term)
    
    if not books:
        sys.exit(0)
    
    # اگر index وارد نشده باشد، لیست را نمایش بده
    if not book_index_str:
        print("\n----- نتایج جستجو -----")
        for b in books:
            print(f"[{b['index']}] {b['title']} - {b['author']} ({b['year']}) - ناشر: {b['publisher']}")
        print("\nبرای دانلود، اکشن را دوباره اجرا کنید و شماره کتاب را در فیلد book_index وارد نمایید.")
        sys.exit(0)
    
    # دانلود کتاب با index مورد نظر
    try:
        book_index = int(book_index_str)
    except ValueError:
        print("book_index باید یک عدد صحیح باشد.")
        sys.exit(1)
    
    selected_book = next((b for b in books if b['index'] == book_index), None)
    if not selected_book:
        print(f"کتاب با ایندکس {book_index} یافت نشد. لطفاً از لیست بالا یکی را انتخاب کنید.")
        sys.exit(1)
    
    print(f"در حال دانلود: {selected_book['title']} - {selected_book['author']}")
    success = download_book(selected_book)
    if success:
        print("دانلود کامل شد. فایل در پوشه downloads مخزن شما قرار خواهد گرفت.")
    else:
        print("دانلود با خطا مواجه شد.")

if __name__ == "__main__":
    main()
