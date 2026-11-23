# Hướng dẫn tích hợp camera báo cáo tấm

Tài liệu này dành cho người lập trình phần mềm camera. Bạn không cần biết về web: chỉ cần biết gửi một **HTTP request** (giống trình duyệt gọi tới một địa chỉ) và đọc kết quả trả về.

## 1. Camera cần làm gì

Mỗi lần camera đọc được mã QR trên một tấm kính, camera gửi **mã tấm** lên server. Server ghi nhận "tấm này đã được tổ X báo cáo" và trả lại thông tin tấm.

Camera không cần đăng nhập. Mỗi camera được cấp sẵn một **API key** (một chuỗi bí mật), server nhận ra camera nào đang gửi nhờ chuỗi đó, và tự biết camera thuộc tổ nào.

## 2. Thông tin bạn sẽ được cấp

Người quản trị hệ thống sẽ đưa bạn 3 thông tin. **Giữ bí mật cả 3**, không đưa lên mạng, không in ra log:

| Thông tin                      | Ví dụ                      | Dùng để                                |
| ------------------------------ | -------------------------- | -------------------------------------- |
| Địa chỉ server (`BASE_URL`)    | `https://gpgo.example.com` | Nơi gửi request tới                    |
| App secret (`APP_SECRET`)      | `a1b2c3...`                | Tạo header `X-App-Token` (mục 4.1)     |
| API key của camera (`API_KEY`) | `9f8e7d...`                | Gửi trong header `X-Api-Key` (mục 4.2) |

Mỗi camera có một API key riêng. Hai camera khác nhau không được dùng chung key, nếu không server sẽ ghi nhận sai camera và sai tổ.

## 3. Request cần gửi

Một HTTP request gồm 4 phần: **phương thức**, **địa chỉ**, **header** (các dòng thông tin kèm theo, dạng `Tên: giá trị`) và **body** (nội dung chính).

| Phần                  | Giá trị                                                       |
| --------------------- | ------------------------------------------------------------- |
| Phương thức           | `POST`                                                        |
| Địa chỉ               | `BASE_URL` + `/api/v1/production/camera/product-item-reports` |
| Header `Content-Type` | `application/json`                                            |
| Header `X-App-Token`  | Chuỗi chữ ký, **tạo mới cho mỗi lần gửi** (mục 4.1)           |
| Header `X-Api-Key`    | `API_KEY` của camera, gửi nguyên văn (mục 4.2)                |
| Body                  | `{"productItemCode": "<mã tấm đọc từ QR>"}`                   |

Ví dụ một request hoàn chỉnh:

```http
POST /api/v1/production/camera/product-item-reports HTTP/1.1
Host: gpgo.example.com
Content-Type: application/json
X-App-Token: 3f9c0e5b7a...(64 ký tự)
X-Api-Key: 9f8e7d...

{"productItemCode": "000000000001"}
```

Body là **JSON**, một định dạng văn bản dạng `{"tên": "giá trị"}`. Ở đây chỉ có một trường `productItemCode`, giá trị là chuỗi đọc được từ mã QR, gửi nguyên văn.

## 4. Hai header bảo mật

### 4.1. `X-App-Token`: chứng minh request đến từ phần mềm hợp lệ

`X-App-Token` là một **chữ ký**: một chuỗi 64 ký tự hex được tính từ `APP_SECRET` và thời điểm gửi. Server tự tính lại theo cùng cách; nếu khớp thì chấp nhận. Chữ ký chỉ có hiệu lực khoảng 1–2 phút, nên **phải tính lại mỗi lần gửi**, không tính một lần rồi dùng mãi.

Công thức tổng:

```text
timestamp   = floor(now_ms / 60000) * 60000
X-App-Token = hex( HMAC_SHA256( key = APP_SECRET,
                                message = timestamp + "\n" + "POST" + "\n" + "/api/v1/production/camera/product-item-reports" ) )
```

Trong đó:

- `now_ms`: thời điểm hiện tại tính bằng mili giây Unix (UTC).
- `"\n"`: ký tự xuống dòng LF.
- `+`: nối chuỗi.
- `hex(...)`: đổi ra chuỗi hex chữ thường, 64 ký tự.

Cách tính, từng bước:

1. **Lấy thời điểm hiện tại**, đổi ra số **mili giây** kể từ 01/01/1970 (Unix time, giờ UTC).

2. **Làm tròn xuống đầu phút**: bỏ phần giây và mili giây. Công thức: `timestamp = floor(ms / 60000) * 60000`.
   Ví dụ: `1763631234567` → `1763631180000`.

3. **Ghép chuỗi cần ký** gồm 3 dòng, nối bằng ký tự xuống dòng `\n` (một ký tự LF, mã 10; **không** dùng `\r\n`, không có dấu cách thừa, không có xuống dòng ở cuối):
   
   ```text
   1763631180000
   POST
   /api/v1/production/camera/product-item-reports
   ```
   
   Dòng 1 là `timestamp`, dòng 2 là phương thức viết hoa `POST`, dòng 3 là **đường dẫn**: phần địa chỉ sau tên miền, bắt đầu bằng `/api`, không có `BASE_URL`, không có `?...`.

4. **Tính HMAC-SHA256** của chuỗi trên, dùng `APP_SECRET` làm khóa (key). Hầu hết ngôn ngữ đều có sẵn hàm này.

5. **Đổi kết quả ra hex chữ thường** (64 ký tự `0-9a-f`). Đó là giá trị của header `X-App-Token`.

Lưu ý:

- **Đồng hồ của máy camera phải đúng giờ** (lệch tối đa khoảng 1 phút). Bật đồng bộ giờ tự động (NTP). Lệch giờ là lý do phổ biến nhất gây lỗi `403 invalid X-App-Token`.
- Múi giờ của máy không ảnh hưởng, vì Unix time luôn tính theo UTC.

### 4.2. `X-Api-Key`: cho server biết camera nào đang gửi

Gửi nguyên văn `API_KEY` được cấp, không mã hóa, không tính toán gì thêm:

```text
X-Api-Key: 9f8e7d...
```

Nếu key bị đổi hoặc thu hồi, server trả `401`. Khi đó liên hệ quản trị viên để lấy key mới.

## 5. Kết quả trả về (response)

Server trả về một **mã trạng thái** (status code, là số) và một body JSON.

### 5.1. Thành công: `200`

```json
{
  "status": "REPORTED",
  "report": {
    "id": "0b7c6e7e-1f7a-4c1e-9d55-8a2f0d7c9b11",
    "logs": [
      {
        "id": "5d1b4a5e-3c2d-4f6a-8b9c-1e2f3a4b5c6d",
        "reportedBy": { "id": "c1a2...", "code": "000120", "name": "Camera Tổ Cắt 1" },
        "reportedAt": "2026-11-20T08:15:30.123456Z"
      }
    ],
    "doneBy": null,
    "doneAt": null
  },
  "productItem": {
    "id": "7e8f...",
    "code": "000000000001",
    "product": {
      "id": "1a2b...",
      "code": "SP001",
      "length": 1200,
      "width": 800,
      "diameter": null,
      "glassShape": null,
      "description": "Kính cường lực 10mm",
      "material": { "id": "3c4d...", "code": "VL01", "name": "Kính trắng 10mm" },
      "order": { "id": "5e6f...", "code": "DH0001" }
    }
  },
  "warning": ""
}
```

Camera thường chỉ cần đọc 3 trường:

| Trường             | Ý nghĩa                                                                                                   |
| ------------------ | --------------------------------------------------------------------------------------------------------- |
| `status`           | Trạng thái tấm sau khi quét. Thành công thì luôn là `REPORTED` (đã báo cáo, chờ xác nhận).                |
| `productItem.code` | Mã tấm server đã ghi nhận. Dùng để đối chiếu với mã vừa quét.                                             |
| `warning`          | Chuỗi rỗng `""` nếu là lần quét đầu tiên. Khác rỗng thì vẫn **thành công**, chỉ để thông báo (bảng dưới). |

Các giá trị `warning` có thể gặp:

| `warning`                                                          | Ý nghĩa                                                           |
| ------------------------------------------------------------------ | ----------------------------------------------------------------- |
| `""`                                                               | Quét lần đầu, bình thường.                                        |
| `Tấm đã được quét trước đó, số lần quét đã tăng`                   | Tấm này đã được quét rồi. Server vẫn ghi thêm một lần quét.       |
| `Tấm đã được xác nhận trước đó, trạng thái chuyển về chờ xác nhận` | Tấm đã được xác nhận xong, nay quét lại nên quay về chờ xác nhận. |
| `Tấm đã bị huỷ trước đó, trạng thái chuyển về chờ xác nhận`        | Tấm đã bị huỷ, nay quét lại nên được khôi phục.                   |

Mỗi lần quét được thêm một phần tử vào `report.logs`. Các trường khác (kích thước, vật liệu, đơn hàng…) chỉ để hiển thị nếu cần.

### 5.2. Lỗi

Khi lỗi, body luôn có dạng:

```json
{ "error": "<thông báo lỗi tiếng Việt>" }
```

| Mã    | `error`                          | Nguyên nhân                                                          | Cách xử lý                              |
| ----- | -------------------------------- | -------------------------------------------------------------------- | --------------------------------------- |
| `400` | `Yêu cầu không hợp lệ: ...`      | Body sai định dạng JSON hoặc thiếu/rỗng `productItemCode`            | Kiểm tra lại body                       |
| `400` | `Camera phải thuộc đúng 1 tổ`    | Camera chưa được gắn tổ hoặc gắn nhiều tổ                            | Báo quản trị viên                       |
| `400` | `Không tìm thấy người xác nhận`  | Tài khoản camera không hợp lệ                                        | Báo quản trị viên                       |
| `401` | `Thiếu API key`                  | Không gửi header `X-Api-Key` hoặc giá trị rỗng                       | Thêm header                             |
| `401` | `API key không hợp lệ`           | Key sai, đã bị đổi/thu hồi, hoặc camera bị khóa/xóa                  | Kiểm tra key, báo quản trị viên         |
| `403` | `X-App-Token header is required` | Không gửi header `X-App-Token`                                       | Thêm header                             |
| `403` | `invalid X-App-Token`            | Chữ ký sai: sai secret, sai chuỗi ký, hoặc **đồng hồ máy lệch giờ**  | Xem mục 4.1, kiểm tra giờ máy           |
| `404` | `Không tìm thấy tấm`             | Mã tấm không có trong hệ thống (đọc QR sai, QR không thuộc hệ thống) | Quét lại; nếu vẫn lỗi thì bỏ qua tấm đó |
| `404` | `Không tìm thấy tổ`              | Tổ của camera đã bị xóa                                              | Báo quản trị viên                       |
| `500` | `Báo cáo tấm thất bại: ...`      | Lỗi phía server                                                      | Thử gửi lại sau vài giây                |

Khuyến nghị cho phần mềm camera:

- **Không gửi lại** khi gặp `400`, `401`, `403`, `404`: gửi lại vẫn lỗi y như cũ. Riêng `403 invalid X-App-Token` thì kiểm tra giờ máy rồi mới thử lại.
- **Có thể gửi lại** khi gặp `500`, khi mất mạng hoặc khi hết thời gian chờ (timeout). Mỗi lần gửi lại phải **tính lại `X-App-Token`**. Đặt timeout khoảng 10 giây.
- Nếu không chắc lần gửi trước đã tới server hay chưa, cứ gửi lại: server chỉ ghi thêm một lần quét và trả `warning` "đã được quét trước đó", không tạo tấm trùng.

## 6. Code mẫu

Thay 3 giá trị `BASE_URL`, `APP_SECRET`, `API_KEY` bằng thông tin được cấp. Nên đọc chúng từ file cấu hình hoặc biến môi trường thay vì viết thẳng vào code.

### Python 3 (cần thư viện `requests`: `pip install requests`)

```python
import hashlib
import hmac
import time

import requests

BASE_URL = "https://gpgo.example.com"
APP_SECRET = "<app secret>"
API_KEY = "<api key của camera>"
PATH = "/api/v1/production/camera/product-item-reports"


def make_app_token(method: str, path: str) -> str:
    ms = int(time.time() * 1000)
    timestamp = ms // 60000 * 60000          # làm tròn xuống đầu phút
    message = f"{timestamp}\n{method}\n{path}"
    return hmac.new(APP_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()


def report(product_item_code: str) -> dict:
    headers = {
        "Content-Type": "application/json",
        "X-App-Token": make_app_token("POST", PATH),
        "X-Api-Key": API_KEY,
    }
    resp = requests.post(BASE_URL + PATH, json={"productItemCode": product_item_code},
                         headers=headers, timeout=10)
    data = resp.json()
    if resp.status_code != 200:
        raise RuntimeError(f"{resp.status_code}: {data.get('error')}")
    return data


result = report("000000000001")
print(result["status"], result["productItem"]["code"], result["warning"])
```

### C# (.NET 6 trở lên)

```csharp
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;

const string BaseUrl = "https://gpgo.example.com";
const string AppSecret = "<app secret>";
const string ApiKey = "<api key của camera>";
const string Path = "/api/v1/production/camera/product-item-reports";

var http = new HttpClient { Timeout = TimeSpan.FromSeconds(10) };

string MakeAppToken(string method, string path)
{
    long ms = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
    long timestamp = ms / 60000 * 60000;                     // làm tròn xuống đầu phút
    string message = $"{timestamp}\n{method}\n{path}";
    using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(AppSecret));
    byte[] hash = hmac.ComputeHash(Encoding.UTF8.GetBytes(message));
    return Convert.ToHexString(hash).ToLowerInvariant();
}

async Task<string> Report(string productItemCode)
{
    var req = new HttpRequestMessage(HttpMethod.Post, BaseUrl + Path)
    {
        Content = JsonContent.Create(new { productItemCode })
    };
    req.Headers.Add("X-App-Token", MakeAppToken("POST", Path));
    req.Headers.Add("X-Api-Key", ApiKey);

    var resp = await http.SendAsync(req);
    string body = await resp.Content.ReadAsStringAsync();
    if (!resp.IsSuccessStatusCode)
        throw new Exception($"{(int)resp.StatusCode}: {body}");
    return body; // JSON như mục 5.1
}

Console.WriteLine(await Report("000000000001"));
```

### Node.js (18 trở lên, không cần cài thêm)

```javascript
const crypto = require("crypto");

const BASE_URL = "https://gpgo.example.com";
const APP_SECRET = "<app secret>";
const API_KEY = "<api key của camera>";
const PATH = "/api/v1/production/camera/product-item-reports";

function makeAppToken(method, path) {
  const timestamp = Math.floor(Date.now() / 60000) * 60000; // làm tròn xuống đầu phút
  const message = `${timestamp}\n${method}\n${path}`;
  return crypto.createHmac("sha256", APP_SECRET).update(message).digest("hex");
}

async function report(productItemCode) {
  const resp = await fetch(BASE_URL + PATH, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-App-Token": makeAppToken("POST", PATH),
      "X-Api-Key": API_KEY,
    },
    body: JSON.stringify({ productItemCode }),
    signal: AbortSignal.timeout(10000),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(`${resp.status}: ${data.error}`);
  return data;
}

report("000000000001").then((r) => console.log(r.status, r.productItem.code, r.warning));
```

### Dòng lệnh (bash + `openssl` + `curl`), để thử nhanh

```bash
BASE_URL="https://gpgo.example.com"
APP_SECRET="<app secret>"
API_KEY="<api key của camera>"
API_PATH="/api/v1/production/camera/product-item-reports"

TS=$(( $(date +%s) / 60 * 60 * 1000 ))
TOKEN=$(printf '%s\n%s\n%s' "$TS" "POST" "$API_PATH" | openssl dgst -sha256 -hmac "$APP_SECRET" | awk '{print $NF}')

curl -sS -X POST "$BASE_URL$API_PATH" \
  -H "Content-Type: application/json" \
  -H "X-App-Token: $TOKEN" \
  -H "X-Api-Key: $API_KEY" \
  -d '{"productItemCode":"000000000001"}'
```

## 7. Kiểm tra cách tính chữ ký

Dùng dữ liệu cố định dưới đây để so kết quả hàm tạo `X-App-Token` của bạn (thay thời gian hiện tại bằng `timestamp` cố định):

| Đầu vào          | Giá trị                                                            |
| ---------------- | ------------------------------------------------------------------ |
| `APP_SECRET`     | `test-secret`                                                      |
| `timestamp`      | `1763631180000`                                                    |
| Phương thức      | `POST`                                                             |
| Đường dẫn        | `/api/v1/production/camera/product-item-reports`                   |
| **Kết quả đúng** | `5b0b785e50ed64bdcfa810bf3b57a9622097f6a14412a9318ec93f20b5233a2b` |

Nếu kết quả khác, thường do một trong các lỗi:

- dùng `\r\n` thay vì `\n`, hoặc có xuống dòng ở cuối chuỗi;
- dùng giây thay vì mili giây, hoặc quên làm tròn xuống đầu phút;
- đường dẫn thiếu `/api` hoặc có cả `https://...`;
- in hex chữ hoa hoặc dùng base64 thay vì hex.

## 8. Tóm tắt

1. Đọc mã QR được chuỗi `productItemCode`.
2. Tính `X-App-Token` từ `APP_SECRET` và thời điểm hiện tại (mục 4.1).
3. Gửi `POST BASE_URL/api/v1/production/camera/product-item-reports` với header `Content-Type`, `X-App-Token`, `X-Api-Key` và body `{"productItemCode": "..."}`.
4. Nhận `200`: thành công, xem `warning` nếu cần. Mã khác: đọc `error` và xử lý theo bảng mục 5.2.
