import requests
from datetime import datetime
from openai import OpenAI
import time
import os
import json
from pathlib import Path
from dotenv import load_dotenv
import re
import base64

load_dotenv()
# OpenAI 클라이언트 초기화 (API 키가 있으면만 사용)
try:
    if os.getenv("OPENAI_API_KEY"):
        client = OpenAI()
    else:
        client = None
except Exception as e:
    print(f"OpenAI 클라이언트 초기화 실패: {e}")
    client = None

# 캐시 파일 경로
CACHE_VERSION = 2
CACHE_DIR = Path(__file__).parent.parent.parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)
CACHE_FILE = CACHE_DIR / "news_cache.json"

# 뉴스 캐시 (메모리에 저장)
_news_cache = {
    "data": None,
    "timestamp": None,
    "ttl": 86400  # 24시간
}

GENERATED_DIR = Path(__file__).parent.parent / "static" / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

def _pick_emoji(title: str) -> str:
    text = (title or "").lower()
    if any(k in text for k in ["ai", "artificial intelligence", "ml", "machine learning"]):
        return "🤖"
    if any(k in text for k in ["cloud", "aws", "gcp", "azure", "datacenter"]):
        return "☁️"
    if any(k in text for k in ["kubernetes", "k8s"]):
        return "🚢"
    if "docker" in text:
        return "🐳"
    if any(k in text for k in ["security", "vulnerability", "breach", "zero-day"]):
        return "🔒"
    if any(k in text for k in ["data", "database", "analytics", "warehouse"]):
        return "📊"
    if any(k in text for k in ["chip", "semiconductor", "gpu", "cpu"]):
        return "🧠"
    if any(k in text for k in ["robot", "automation"]):
        return "🦾"
    return "📰"

def _build_image_prompt(title: str) -> str:
    text = (title or "").strip()
    return (
        "Create a clean, modern, editorial illustration for a tech news article. "
        "Style: flat illustration, minimal shapes, subtle gradients. "
        "No text, no logos, no brand marks. "
        "High-contrast, minimal, professional. "
        "Theme: " + text
    )

def _clean_summary(text: str) -> str:
    if not text:
        return ""
    # Remove markdown headers and bullets
    cleaned = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    cleaned = re.sub(r"^[\-\*\u2022]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.replace("**", "").replace("__", "")
    # Collapse whitespace
    cleaned = re.sub(r"\n{2,}", "\n", cleaned).strip()
    return cleaned

def _parse_headline_and_summary(gpt_content: str, fallback_title: str):
    headline = fallback_title
    summary = ""
    detail_lines = []
    in_detail = False
    after_summary = False
    for line in gpt_content.splitlines():
        stripped = line.strip()
        if stripped.startswith("HEADLINE:"):
            headline = line.split("HEADLINE:", 1)[1].strip()
        elif stripped.startswith("SUMMARY:"):
            summary = line.split("SUMMARY:", 1)[1].strip()
            after_summary = True
        elif stripped.startswith("DETAIL:"):
            in_detail = True
            after_summary = False
            rest = line.split("DETAIL:", 1)[1].strip()
            if rest:
                detail_lines.append(rest)
        elif in_detail:
            detail_lines.append(line)
        elif after_summary:
            # If model omitted DETAIL:, treat remaining lines as detail
            detail_lines.append(line)
    summary = _clean_summary(summary)
    detail = "\n".join(detail_lines).strip()
    return headline or fallback_title, summary, detail

def _safe_image_name(raw_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", str(raw_id))
    return f"news_{safe}.png"

def _generate_detail_markdown(title: str):
    if not client:
        return ""
    try:
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "기술 기사 제목을 보고 아래 형식의 한국어 상세 요약만 작성하세요. "
                        "형식과 줄바꿈을 지켜야 합니다.\n"
                        "SUMMARY: [결론 한 문장]\n"
                        "## 핵심 주장\n"
                        "- [주장 1]\n"
                        "- [주장 2]\n"
                        "- [주장 3]\n"
                        "## 왜 중요한가\n"
                        "- [실무/운영 관점 의미]\n"
                        "- [현재 기술 흐름에서의 중요성]"
                    )
                },
                {
                    "role": "user",
                    "content": f"제목: {title}"
                }
            ],
            temperature=0.7,
            max_tokens=800
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"DETAIL 생성 실패: {e}")
        return ""

def _generate_gpt_image(prompt: str, raw_id: str):
    if not client:
        return None

    filename = _safe_image_name(raw_id)
    file_path = GENERATED_DIR / filename
    if file_path.exists():
        return {
            "image_url": f"/static/generated/{filename}",
            "image_alt": prompt
        }

    try:
        response = client.images.generate(
            model="gpt-image-1-mini",
            prompt=prompt,
            size="1536x1024",
            quality="low"
        )
        if not response or not getattr(response, "data", None):
            return None

        image_base64 = response.data[0].b64_json
        if not image_base64:
            return None

        file_path.write_bytes(base64.b64decode(image_base64))
        return {
            "image_url": f"/static/generated/{filename}",
            "image_alt": prompt
        }
    except Exception as e:
        print(f"GPT 이미지 생성 실패: {e}")
        return None

def _enrich_news_item(item: dict, title: str):
    item["emoji"] = _pick_emoji(title)
    prompt = _build_image_prompt(title)
    image_data = _generate_gpt_image(prompt, item.get("id"))
    if image_data and image_data.get("image_url"):
        item.update(image_data)
    return item

def _load_cache_from_file():
    """파일에서 캐시 로드"""
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                if cache_data.get("version") != CACHE_VERSION:
                    return False
                _news_cache["data"] = cache_data.get("data")
                _news_cache["timestamp"] = cache_data.get("timestamp")
                return _is_cache_valid()
        except Exception as e:
            print(f"캐시 로드 실패: {e}")
    return False

def _save_cache_to_file():
    """파일에 캐시 저장"""
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "version": CACHE_VERSION,
                "data": _news_cache["data"],
                "timestamp": _news_cache["timestamp"]
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"캐시 저장 실패: {e}")

def _is_cache_valid():
    """캐시가 유효한지 확인"""
    if _news_cache["data"] is None or _news_cache["timestamp"] is None:
        return False
    return (time.time() - _news_cache["timestamp"]) < _news_cache["ttl"]

def get_tech_news():
    """
    HackerNews API에서 최신 기술 뉴스 3개를 가져오고,
    GPT를 사용해 자극적인 제목과 한글 요약을 생성합니다.
    메모리와 파일 캐싱을 통해 성능을 최적화합니다.
    """
    print("[INFO] get_tech_news() 호출됨")
    
    # 메모리 캐시 확인
    if _is_cache_valid():
        print("[INFO] 메모리 캐시에서 반환")
        return _news_cache["data"]
    
    # 파일 캐시 로드 시도
    if _load_cache_from_file():
        print("[INFO] 파일 캐시에서 로드됨")
        return _news_cache["data"]
    
    print("[INFO] 새로운 뉴스 데이터 생성 중...")
    try:
        # HackerNews API에서 상위 스토리 ID 가져오기
        top_stories_url = "https://hacker-news.firebaseio.com/v0/topstories.json"
        response = requests.get(top_stories_url, timeout=5)
        top_story_ids = response.json()[:5]  # 상위 15개 가져오기
        
        news_items = []
        story_url = "https://hacker-news.firebaseio.com/v0/item/{}.json"
        
        for story_id in top_story_ids:
            try:
                item_response = requests.get(story_url.format(story_id), timeout=3)
                item = item_response.json()
                
                # 필요한 필드가 있는지 확인
                if "title" in item and "url" in item:
                    original_title = item.get("title", "")
                    
                    # GPT를 사용해 자극적인 제목과 한글 요약 생성 (API 키가 있을 때만)
                    try:
                        if client:
                            gpt_response = client.chat.completions.create(
                                model="gpt-3.5-turbo",
                                messages=[
                                    {
                                        "role": "system",
                                        "content": (
                                            "당신은 '감테크' YouTube 채널의 시니어 기술 에디터입니다. "
                                            "20-30대 개발자와 학생들이 '오, 이거 봐야겠다!'라고 생각하게 만드는 것이 목표입니다.\n\n"
                                            
                                            "## 헤드라인 작성 원칙\n"
                                            "- 기술 트렌드의 '진짜 의미'를 짚어내세요 (예: '이거 안 쓰면 뒤처진다', '업계 판도가 바뀐다')\n"
                                            "- 구체적 숫자나 임팩트를 넣으세요 (예: '성능 3배', '개발 시간 50% 단축')\n"
                                            "- 실무자의 고민을 건드리세요 (예: '면접에서 물어본다', '이제 legacy 된다')\n"
                                            "- 이모지 1-2개로 시선 집중 (🚀⚡🔥💀🎯🤯)\n\n"
                                            
                                            "## 요약 작성 원칙\n"
                                            "- 첫 문장: 핵심 결론을 단정적으로 ('~입니다', '~됩니다')\n"
                                            "- 두 번째: 왜 지금 중요한지 실무 맥락 ('현업에서는~', '이미 대기업들은~')\n"
                                            "- 세 번째: 독자가 취할 액션 힌트 ('주목해야 할 이유는~', '바뀌는 건~')\n"
                                            "- 마크다운 없이 자연스러운 한국어 2-3문장\n\n"
                                            
                                            "## 상세 내용 구조\n"
                                            "DETAIL: 뒤에는 반드시 마크다운으로 아래 형식을 따르세요:\n\n"
                                            "SUMMARY: [한 줄로 핵심 정리 - 강렬하게]\n\n"
                                            "## 🎯 핵심 포인트\n"
                                            "- [구체적 변화/수치/사례 1]\n"
                                            "- [실무 영향 2]\n"
                                            "- [기술적 의의 3]\n\n"
                                            "## 💡 왜 지금 주목해야 하나\n"
                                            "- [현업 관점: 채용/면접/프로젝트에서 어떻게 쓰이는가]\n"
                                            "- [기술 트렌드: 업계가 어디로 가고 있는가]\n"
                                            "- [러닝 포인트: 개발자가 배워야 할 것]\n\n"
                                            
                                            "## 출력 형식 (반드시 지킬 것)\n"
                                            "HEADLINE: [자극적이고 구체적인 헤드라인]\n"
                                            "SUMMARY: [2-3문장의 명확한 한국어 요약, 마크다운 없음]\n"
                                            "DETAIL:\n"
                                            "SUMMARY: [한 줄 핵심]\n"
                                            "## 🎯 핵심 포인트\n...\n"
                                            "## 💡 왜 지금 주목해야 하나\n...\n\n"
                                            
                                            "예시 톤:\n"
                                            "❌ 나쁜 예: 'Kubernetes 1.30이 출시되었습니다.'\n"
                                            "✅ 좋은 예: '🚀 쿠버네티스 1.30 충격! 메모리 사용량 40% 감소, 이제 중소기업도 쓴다'\n\n"
                                            
                                            "❌ 나쁜 예: 'AI 모델이 개선되었습니다.'\n"
                                            "✅ 좋은 예: '🤖 GPT-5 실화냐? 코딩 테스트 만점, 시니어 개발자 위기설'\n\n"
                                            
                                            "기억하세요: 독자는 바쁜 현업 개발자입니다. "
                                            "3초 안에 '아, 이거 내가 알아야 하는 거네' 느끼게 만드세요!"
                                        )
                                    },
                                    {
                                        "role": "user",
                                        "content": (
                                            f"다음 영어 기술 글 제목을 기반으로 "
                                            f"자극적인 헤드라인과 한국어 요약을 작성해줘.\n\n"
                                            f"원문 제목:\n{original_title}"
                                        )
                                    }
                                ],
                                temperature=0.7,
                                max_tokens=2500
                            )
                            
                            gpt_content = gpt_response.choices[0].message.content.strip()
                            print(f"[DEBUG] GPT 응답: {gpt_content}")
                            
                            # GPT 응답 파싱
                            new_title, description, detail_markdown = _parse_headline_and_summary(
                                gpt_content, original_title
                            )
                            
                            # detail_markdown이 없으면 추가 생성
                            if not detail_markdown:
                                detail_markdown = _generate_detail_markdown(original_title)
                            
                            # 파싱 실패 시 폴백
                            if not description:
                                description = f"Posted by {item.get('by', 'Anonymous')} with {item.get('score', 0)} points"
                        else:
                            # API 키가 없으면 원본 사용
                            print("[DEBUG] OpenAI API 키가 없습니다")
                            new_title = original_title
                            description = f"Posted by {item.get('by', 'Anonymous')} with {item.get('score', 0)} points"
                            detail_markdown = ""
                        
                        # 새 아이템 생성 (모든 필드 포함)
                        new_item = {
                            "id": story_id,
                            "title": new_title,
                            "original_title": original_title,
                            "source": "HackerNews",
                            "url": item.get("url", ""),
                            "date": datetime.now().strftime("%Y-%m-%d"),
                            "description": description,
                            "summary": description,  # summary 필드 추가
                            "short_description": description[:160] if description else "",  # short_description 필드 추가
                            "detail_markdown": detail_markdown if detail_markdown else "",  # detail_markdown 필드 추가
                            "score": item.get("score", 0)
                        }
                        
                        # 리스트에 추가하고 이미지/이모지 enrichment
                        news_items.append(new_item)
                        _enrich_news_item(news_items[-1], original_title or new_title)
                        
                        if len(news_items) >= 3:
                            break
                            
                    except Exception as e:
                        # GPT 호출 실패시 원본 데이터 사용
                        print(f"GPT 처리 실패: {e}")
                        new_item = {
                            "id": story_id,
                            "title": original_title,
                            "original_title": original_title,
                            "source": "HackerNews",
                            "url": item.get("url", ""),
                            "date": datetime.now().strftime("%Y-%m-%d"),
                            "description": f"Posted by {item.get('by', 'Anonymous')} with {item.get('score', 0)} points",
                            "summary": f"Posted by {item.get('by', 'Anonymous')} with {item.get('score', 0)} points",
                            "short_description": f"Posted by {item.get('by', 'Anonymous')}",
                            "detail_markdown": "",
                            "score": item.get("score", 0)
                        }
                        
                        news_items.append(new_item)
                        _enrich_news_item(news_items[-1], original_title)
                        
                        if len(news_items) >= 3:
                            break
            except:
                continue
        
        result = news_items if news_items else get_fallback_news()
        
        # 캐시에 저장 (메모리 + 파일)
        _news_cache["data"] = result
        _news_cache["timestamp"] = time.time()
        _save_cache_to_file()
        
        return result
    except:
        # 뉴스를 가져오지 못한 경우 기본 뉴스 반환
        result = get_fallback_news()
        
        # 폴백 뉴스도 캐시 (메모리 + 파일)
        _news_cache["data"] = result
        _news_cache["timestamp"] = time.time()
        _save_cache_to_file()
        
        return result

def get_fallback_news():
    """
    API 요청 실패 시 기본 뉴스를 반환합니다.
    """
    items = [
        {
            "id": "fallback_1",
            "title": "🚀 쿠버네티스 1.29 출시! 성능 혁신의 새로운 시대",
            "original_title": "Kubernetes 1.29 Release",
            "source": "Kubernetes Blog",
            "url": "https://kubernetes.io/blog/",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "description": "최신 버전에서 성능이 개선되었고 새로운 API가 추가되었습니다. 컨테이너 오케스트레이션의 미래를 만나보세요.",
            "summary": "최신 버전에서 성능이 개선되었고 새로운 API가 추가되었습니다. 컨테이너 오케스트레이션의 미래를 만나보세요.",
            "short_description": "최신 버전에서 성능이 개선되었고 새로운 API가 추가되었습니다.",
            "detail_markdown": "## 핵심 주장\n- 성능 개선\n- 새로운 API 추가\n\n## 왜 중요한가\n- 컨테이너 오케스트레이션의 발전",
            "score": 100
        },
        {
            "id": "fallback_2",
            "title": "🤖 Docker Desktop에 AI 기능 통합! 개발 생산성 폭증",
            "original_title": "Docker Desktop AI Integration",
            "source": "Docker",
            "url": "https://www.docker.com/blog/",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "description": "Docker Desktop에 AI 기반의 이미지 분석 기능이 추가되었습니다. 이제 더 똑똑한 컨테이너 관리가 가능합니다.",
            "summary": "Docker Desktop에 AI 기반의 이미지 분석 기능이 추가되었습니다. 이제 더 똑똑한 컨테이너 관리가 가능합니다.",
            "short_description": "Docker Desktop에 AI 기반의 이미지 분석 기능이 추가되었습니다.",
            "detail_markdown": "## 핵심 주장\n- AI 기능 통합\n- 생산성 향상\n\n## 왜 중요한가\n- 개발 워크플로우 개선",
            "score": 85
        },
        {
            "id": "fallback_3",
            "title": "⚡ 마이크로서비스 아키텍처가 엔터프라이즈를 제압",
            "original_title": "Microservices Architecture Enterprise Trend",
            "source": "DevOps Digest",
            "url": "https://devops.com/",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "description": "마이크로서비스 기반 아키텍처가 엔터프라이즈 환경에서 주류가 되고 있습니다. 분산 시스템의 새로운 패러다임입니다.",
            "summary": "마이크로서비스 기반 아키텍처가 엔터프라이즈 환경에서 주류가 되고 있습니다. 분산 시스템의 새로운 패러다임입니다.",
            "short_description": "마이크로서비스 기반 아키텍처가 엔터프라이즈 환경에서 주류가 되고 있습니다.",
            "detail_markdown": "## 핵심 주장\n- 마이크로서비스 아키텍처 채택 증가\n- 엔터프라이즈 환경 적용\n\n## 왜 중요한가\n- 분산 시스템의 미래",
            "score": 72
        }
    ]
    for item in items:
        _enrich_news_item(item, item.get("original_title") or item.get("title"))
    return items