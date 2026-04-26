import os
from supabase import create_client

# 這些變數之後會設定在 GitHub Secrets
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY") # 注意：上傳需使用 Service Role Key
supabase = create_client(url, key)

def upload_model(file_path, bucket_name):
    file_name = os.path.basename(file_path)
    with open(file_path, 'rb') as f:
        # upsert=True 代表如果檔案已存在則覆蓋
        response = supabase.storage.from_(bucket_name).upload(
            path=file_name, 
            file=f, 
            file_options={"x-upsert": "true", "content-type": "application/octet-stream"}
        )
    print(f"✅ 模型 {file_name} 已上傳至 Supabase Storage")

if __name__ == "__main__":
    upload_model("youbike_model.pkl", "models")