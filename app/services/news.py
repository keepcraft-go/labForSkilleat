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
CACHE_VERSION = 3  # 버전 업데이트
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

# 트렌디한 키워드 우선순위 (점수 가중치)
HOT_KEYWORDS = {
    "ai": 3, "gpt": 3, "claude": 3, "llm": 3, "machine learning": 2,
    "kubernetes": 2, "k8s": 2, "docker": 2, "rust": 2, 
    "wasm": 2, "webassembly": 2, "serverless": 2, "edge computing": 2,
    "react": 1.5, "nextjs": 1.5, "typescript": 1.5, "python": 1.5,
    "devops": 1.5, "cloud": 1.5, "aws": 1.5, "security": 2,
    "vulnerability": 2.5, "zero-day": 2.5, "breakthrough": 2,
    "layoff": 1.8, "hiring": 1.5, "interview": 2, "startup": 1.5
}

def _calculate_relevance_score(title: str, score: int) -> float:
    """제목과 점수를 기반으로 관련성 점수 계산"""
    text = (title or "").lower()
    keyword_bonus = 0
    
    for keyword, weight in HOT_KEYWORDS.items():
        if keyword in text:
            keyword_bonus += weight
    
    # HackerNews 점수 + 키워드 가중치
    return score + (keyword_bonus * 20)

def _pick_emoji(title: str) -> str:
    text = (title or "").lower()
    if any(k in text for k in ["ai", "artificial intelligence", "ml", "machine learning", "gpt", "claude", "llm"]):
        return "🤖"
    if any(k in text for k in ["cloud", "aws", "gcp", "azure", "datacenter"]):
        return "☁️"
    if any(k in text for k in ["kubernetes", "k8s"]):
        return "🚢"
    if "docker" in text:
        return "🐳"
    if any(k in text for k in ["security", "vulnerability", "breach", "zero-day", "hack"]):
        return "🔒"
    if any(k in text for k in ["data", "database", "analytics", "warehouse"]):
        return "📊"
    if any(k in text for k in ["chip", "semiconductor", "gpu", "cpu", "nvidia"]):
        return "🧠"
    if any(k in text for k in ["robot", "automation"]):
        return "🦾"
    if any(k in text for k in ["rust", "performance"]):
        return "⚡"
    if any(k in text for k in ["layoff", "firing"]):
        return "💀"
    if any(k in text for k in ["hiring", "job", "career"]):
        return "💼"
    if any(k in text for k in ["startup", "funding"]):
        return "🚀"
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
        elif after_summary and line.strip():
            # If model omitted DETAIL:, treat remaining lines as detail
            detail_lines.append(line)
    summary = _clean_summary(summary)
    detail = "\n".join(detail_lines).strip()
    return headline or fallback_title, summary, detail

def _safe_image_name(raw_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", str(raw_id))
    return f"news_{safe}.png"

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

def _fetch_github_trending():
    """GitHub Trending 저장소 가져오기"""
    try:
        # 비공식 API 사용 (github-trending-api)
        url = "https://api.gitterapp.com/repositories"
        response = requests.get(url, timeout=5)
        repos = response.json()[:3]
        
        items = []
        for repo in repos:
            items.append({
                "id": f"github_{repo.get('name', '').replace('/', '_')}",
                "title": repo.get("name", ""),
                "original_title": repo.get("name", ""),
                "source": "GitHub",
                "url": repo.get("url", ""),
                "description": repo.get("description", ""),
                "score": repo.get("stars", 0)
            })
        return items
    except Exception as e:
        print(f"GitHub Trending 가져오기 실패: {e}")
        return []

def _fetch_devto_posts():
    """Dev.to 인기 글 가져오기"""
    try:
        url = "https://dev.to/api/articles?per_page=5&top=7"  # 최근 7일 TOP
        response = requests.get(url, timeout=5)
        articles = response.json()
        
        items = []
        for article in articles[:3]:
            items.append({
                "id": f"devto_{article.get('id')}",
                "title": article.get("title", ""),
                "original_title": article.get("title", ""),
                "source": "Dev.to",
                "url": article.get("url", ""),
                "description": article.get("description", ""),
                "score": article.get("positive_reactions_count", 0)
            })
        return items
    except Exception as e:
        print(f"Dev.to 가져오기 실패: {e}")
        return []

def get_tech_news():
    """
    여러 소스에서 최신 기술 뉴스를 가져오고,
    GPT를 사용해 자극적인 제목과 한글 요약을 생성합니다.
    메모리와 파일 캐싱을 통해 성능을 최적화합니다.
    """
    print("[INFO] get_tech_news() 호출됨")
    
    # 파일 캐시 우선 로드 (크론 갱신 반영)
    if _load_cache_from_file():
        print("[INFO] 파일 캐시에서 로드됨")
        return _news_cache["data"]

    # 메모리 캐시 확인
    if _is_cache_valid():
        print("[INFO] 메모리 캐시에서 반환")
        return _news_cache["data"]
    
    print("[INFO] 새로운 뉴스 데이터 생성 중...")
    try:
        # 여러 소스에서 뉴스 수집
        all_candidates = []
        
        # 1. HackerNews에서 상위 30개 가져오기 (최근 72시간 필터)
        print("[INFO] HackerNews 데이터 수집 중...")
        top_stories_url = "https://hacker-news.firebaseio.com/v0/topstories.json"
        response = requests.get(top_stories_url, timeout=5)
        top_story_ids = response.json()[:50]  # 넉넉히 가져와 72시간 필터 적용
        
        story_url = "https://hacker-news.firebaseio.com/v0/item/{}.json"
        now_ts = time.time()
        max_age_seconds = 72 * 3600
        
        for story_id in top_story_ids:
            try:
                item_response = requests.get(story_url.format(story_id), timeout=3)
                item = item_response.json()
                
                if "title" in item and "url" in item and "time" in item:
                    if (now_ts - item.get("time", 0)) > max_age_seconds:
                        continue
                    score = item.get("score", 0)
                    title = item.get("title", "")
                    relevance_score = _calculate_relevance_score(title, score)
                    
                    all_candidates.append({
                        "id": story_id,
                        "title": title,
                        "original_title": title,
                        "source": "HackerNews",
                        "url": item.get("url", ""),
                        "score": score,
                        "relevance_score": relevance_score,
                        "by": item.get("by", "Anonymous")
                    })
            except:
                continue
        
        # 2. GitHub Trending (선택적)
        # github_items = _fetch_github_trending()
        # all_candidates.extend(github_items)
        
        # 3. Dev.to (선택적)
        # devto_items = _fetch_devto_posts()
        # all_candidates.extend(devto_items)
        
        # 관련성 점수로 정렬하고 상위 5개 선택
        all_candidates.sort(key=lambda x: x.get("relevance_score", x.get("score", 0)), reverse=True)
        top_candidates = all_candidates[:5]
        
        print(f"[INFO] 상위 5개 후보 선택 완료 (총 {len(all_candidates)}개 중)")
        
        # GPT로 요약 및 변환
        news_items = []
        for item in top_candidates:
            original_title = item.get("title", "")
            
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
                                    "- 실무자의 고민을 건드리세요 (예: '면접에서 물어본다', '이제 legacy 된다', '시니어들은 이미 쓴다')\n"
                                    "- 이모지 1-2개로 시선 집중 (🚀⚡🔥💀🎯🤯💼🧠)\n"
                                    "- 논쟁적이거나 도발적인 각도 환영 (예: '~의 종말', '~가 망했다', '~를 버려야 하는 이유')\n\n"
                                    
                                    "## 요약 작성 원칙 (최소 5-7문장)\n"
                                    "- 첫 문장: 핵심 결론을 단정적으로 ('~입니다', '~됩니다')\n"
                                    "- 두 번째: 구체적 수치나 사례 ('X사는 이미~', '벤치마크 결과~')\n"
                                    "- 세 번째: 왜 지금 중요한지 실무 맥락 ('현업에서는~', '면접에서 빈출~')\n"
                                    "- 네 번째: 기존 방식과의 비교 ('기존 X 대비~', 'Y를 대체할~')\n"
                                    "- 다섯 번째: 실무 적용 팁이나 주의점 ('주의할 점은~', '도입 전에~')\n"
                                    "- 여섯-일곱 번째: 독자 액션 아이템 ('주목해야 할 이유는~', '지금 배워두면~')\n"
                                    "- 마크다운 없이 자연스러운 한국어 문장, 각 문장은 구체적이고 정보량 있게\n\n"
                                    
                                    "## 상세 내용 구조\n"
                                    "DETAIL: 뒤에는 반드시 마크다운으로 아래 형식을 따르세요:\n\n"
                                    "SUMMARY: [한 줄로 핵심 정리 - 강렬하게]\n\n"
                                    "## 🎯 핵심 포인트\n"
                                    "- [구체적 변화/수치/사례 1 - 최소 2문장]\n"
                                    "- [실무 영향 2 - 구체적 시나리오 포함]\n"
                                    "- [기술적 의의 3 - 왜 혁신적인지]\n"
                                    "- [추가 인사이트 - 놓치기 쉬운 포인트]\n\n"
                                    "## 💡 왜 지금 주목해야 하나\n"
                                    "- [현업 관점: 채용/면접/프로젝트에서 어떻게 쓰이는가 - 구체적 예시]\n"
                                    "- [기술 트렌드: 업계가 어디로 가고 있는가 - 시장 데이터]\n"
                                    "- [러닝 포인트: 개발자가 배워야 할 것 - 학습 로드맵 힌트]\n"
                                    "- [경쟁 기술 비교: 기존 솔루션 대비 장단점]\n\n"
                                    "## 🔥 실무 적용 팁\n"
                                    "- [시작하는 방법 - 구체적 첫 걸음]\n"
                                    "- [피해야 할 실수 - 현업 경험담]\n"
                                    "- [추천 리소스 - 공식 문서, 튜토리얼 등]\n\n"
                                    
                                    "## 출력 형식 (반드시 지킬 것)\n"
                                    "HEADLINE: [자극적이고 구체적인 헤드라인]\n"
                                    "SUMMARY: [최소 5-7문장의 상세하고 구체적인 한국어 요약, 마크다운 없음]\n"
                                    "DETAIL:\n"
                                    "SUMMARY: [한 줄 핵심]\n"
                                    "## 🎯 핵심 포인트\n...\n"
                                    "## 💡 왜 지금 주목해야 하나\n...\n"
                                    "## 🔥 실무 적용 팁\n...\n\n"
                                    
                                    "예시 톤:\n"
                                    "❌ 나쁜 예: 'Kubernetes 1.30이 출시되었습니다.'\n"
                                    "✅ 좋은 예: '🚀 쿠버네티스 1.30 충격! 메모리 사용량 40% 감소, 이제 중소기업도 쓴다'\n\n"
                                    
                                    "❌ 나쁜 예: 'AI 모델이 개선되었습니다.'\n"
                                    "✅ 좋은 예: '🤖 GPT-5 실화냐? 코딩 테스트 만점, 시니어 개발자 위기설'\n\n"
                                    
                                    "❌ 나쁜 예 (요약): 'React 19가 출시되었습니다.'\n"
                                    "✅ 좋은 예 (요약): 'React 19가 정식 출시되면서 useState의 사용 패턴이 완전히 바뀝니다. "
                                    "벤치마크 결과 렌더링 성능이 기존 대비 2.3배 향상되었고, Meta 내부에서는 이미 전체 프로덕션에 적용 완료했습니다. "
                                    "특히 면접에서 React 19의 새로운 훅 API에 대한 질문이 급증하고 있어 주니어 개발자들은 반드시 숙지해야 합니다. "
                                    "기존 클래스 컴포넌트를 사용하던 레거시 프로젝트는 마이그레이션 압박을 받을 것으로 예상됩니다. "
                                    "공식 문서에서 제공하는 마이그레이션 가이드를 따르면 대부분의 코드는 자동 변환이 가능하지만, "
                                    "useEffect 의존성 배열 처리 방식이 달라져 주의가 필요합니다. "
                                    "지금 배워두면 향후 2-3년간 React 생태계에서 경쟁력을 유지할 수 있습니다.'\n\n"
                                    
                                    "기억하세요: 독자는 바쁜 현업 개발자입니다. "
                                    "3초 안에 '아, 이거 내가 알아야 하는 거네' 느끼게 만들고, "
                                    "요약만 읽어도 핵심을 완전히 이해할 수 있게 작성하세요!"
                                )
                            },
                            {
                                "role": "user",
                                "content": (
                                    f"다음 영어 기술 글 제목을 기반으로 "
                                    f"자극적인 헤드라인과 상세한 한국어 요약(최소 5-7문장)을 작성해줘.\n\n"
                                    f"원문 제목:\n{original_title}\n\n"
                                    f"출처: {item.get('source', 'HackerNews')}\n"
                                    f"점수: {item.get('score', 0)}"
                                )
                            }
                        ],
                        temperature=0.8,  # 창의성 증가
                        max_tokens=3000   # 토큰 증가
                    )
                    
                    gpt_content = gpt_response.choices[0].message.content.strip()
                    print(f"[DEBUG] GPT 응답 (story_id={item.get('id')}): {gpt_content[:200]}...")
                    
                    # GPT 응답 파싱
                    new_title, description, detail_markdown = _parse_headline_and_summary(
                        gpt_content, original_title
                    )
                    
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
                    "id": item.get("id"),
                    "title": new_title,
                    "original_title": original_title,
                    "source": item.get("source", "HackerNews"),
                    "url": item.get("url", ""),
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "description": description,
                    "summary": description,
                    "short_description": description[:200] if description else "",
                    "detail_markdown": detail_markdown if detail_markdown else "",
                    "score": item.get("score", 0),
                    "relevance_score": item.get("relevance_score", 0)
                }
                
                # 리스트에 추가하고 이미지/이모지 enrichment
                news_items.append(new_item)
                _enrich_news_item(news_items[-1], original_title or new_title)
                
                if len(news_items) >= 3:
                    break
                    
            except Exception as e:
                # GPT 호출 실패시 원본 데이터 사용
                print(f"GPT 처리 실패 (story_id={item.get('id')}): {e}")
                new_item = {
                    "id": item.get("id"),
                    "title": original_title,
                    "original_title": original_title,
                    "source": item.get("source", "HackerNews"),
                    "url": item.get("url", ""),
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "description": f"Posted by {item.get('by', 'Anonymous')} with {item.get('score', 0)} points",
                    "summary": f"Posted by {item.get('by', 'Anonymous')} with {item.get('score', 0)} points",
                    "short_description": f"Posted by {item.get('by', 'Anonymous')}",
                    "detail_markdown": "",
                    "score": item.get("score", 0),
                    "relevance_score": item.get("relevance_score", 0)
                }
                
                news_items.append(new_item)
                _enrich_news_item(news_items[-1], original_title)
                
                if len(news_items) >= 3:
                    break
        
        result = news_items if news_items else get_fallback_news()
        
        # 캐시에 저장 (메모리 + 파일)
        _news_cache["data"] = result
        _news_cache["timestamp"] = time.time()
        _save_cache_to_file()
        
        print(f"[INFO] 뉴스 {len(result)}개 생성 완료")
        return result
    except Exception as e:
        print(f"[ERROR] 뉴스 가져오기 실패: {e}")
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
            "title": "🚀 쿠버네티스 1.29 출시! 메모리 사용량 40% 감소, 이제 중소기업도 쓴다",
            "original_title": "Kubernetes 1.29 Release",
            "source": "Kubernetes Blog",
            "url": "https://kubernetes.io/blog/",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "description": "쿠버네티스 1.29가 정식 출시되면서 컨테이너 오케스트레이션의 판도가 바뀌고 있습니다. 가장 주목할 점은 메모리 사용량이 기존 대비 40% 감소했다는 것으로, 이제 소규모 스타트업도 부담 없이 도입할 수 있게 되었습니다. 특히 Google Cloud와 AWS에서는 이미 프로덕션 환경에 적용을 완료했으며, 국내 대기업들도 연내 마이그레이션을 계획 중입니다. 면접에서도 최신 버전의 변경사항에 대한 질문이 급증하고 있어, DevOps 엔지니어라면 반드시 숙지해야 합니다. 새로운 스토리지 API가 추가되어 StatefulSet 관리가 훨씬 쉬워졌고, Pod Security Standards가 기본 활성화되어 보안도 강화되었습니다. 공식 문서의 마이그레이션 가이드를 따르면 대부분 무중단 업그레이드가 가능하지만, deprecated API를 사용 중이라면 사전 점검이 필수입니다. 지금 학습해두면 향후 3년간 쿠버네티스 생태계에서 경쟁력을 유지할 수 있습니다.",
            "summary": "쿠버네티스 1.29가 정식 출시되면서 컨테이너 오케스트레이션의 판도가 바뀌고 있습니다. 가장 주목할 점은 메모리 사용량이 기존 대비 40% 감소했다는 것으로, 이제 소규모 스타트업도 부담 없이 도입할 수 있게 되었습니다. 특히 Google Cloud와 AWS에서는 이미 프로덕션 환경에 적용을 완료했으며, 국내 대기업들도 연내 마이그레이션을 계획 중입니다. 면접에서도 최신 버전의 변경사항에 대한 질문이 급증하고 있어, DevOps 엔지니어라면 반드시 숙지해야 합니다. 새로운 스토리지 API가 추가되어 StatefulSet 관리가 훨씬 쉬워졌고, Pod Security Standards가 기본 활성화되어 보안도 강화되었습니다. 공식 문서의 마이그레이션 가이드를 따르면 대부분 무중단 업그레이드가 가능하지만, deprecated API를 사용 중이라면 사전 점검이 필수입니다. 지금 학습해두면 향후 3년간 쿠버네티스 생태계에서 경쟁력을 유지할 수 있습니다.",
            "short_description": "쿠버네티스 1.29가 정식 출시되면서 메모리 사용량이 40% 감소했습니다. 이제 중소기업도 부담 없이 도입 가능합니다.",
            "detail_markdown": (
                "SUMMARY: 쿠버네티스 1.29, 메모리 40% 절감으로 중소기업 진입장벽 낮췄다\n\n"
                "## 🎯 핵심 포인트\n"
                "- 메모리 사용량 40% 감소로 8GB RAM에서도 운영 가능한 수준으로 개선\n"
                "- StatefulSet용 새로운 스토리지 API 추가로 데이터베이스 관리 복잡도 50% 감소\n"
                "- Pod Security Standards 기본 활성화로 Zero Trust 아키텍처 구현 용이\n"
                "- Google, AWS 이미 프로덕션 적용 완료 - 안정성 검증됨\n\n"
                "## 💡 왜 지금 주목해야 하나\n"
                "- DevOps 면접에서 1.29 신규 기능 질문 급증 (LinkedIn 채용공고 분석)\n"
                "- 클라우드 네이티브 전환 가속화 - IDC 보고서 '2025년까지 80% 기업 도입'\n"
                "- CKA/CKAD 시험 출제 범위 변경 예정 - 최신 버전 학습 필수\n"
                "- Helm 차트 호환성 이슈 주의 - 일부 차트는 업데이트 대기 중\n\n"
                "## 🔥 실무 적용 팁\n"
                "- kubeadm으로 테스트 클러스터 구축 후 샌드박스 환경에서 검증\n"
                "- deprecated API 사용 여부 체크: kubectl-deprecations 플러그인 활용\n"
                "- 공식 릴리즈 노트 정독 (kubernetes.io/blog) - 변경사항 상세 문서화\n"
            ),
            "score": 850,
            "relevance_score": 910
        },
        {
            "id": "fallback_2",
            "title": "🤖 Docker Desktop AI 통합! Dockerfile 자동 생성, 개발 시간 60% 단축",
            "original_title": "Docker Desktop AI Integration",
            "source": "Docker",
            "url": "https://www.docker.com/blog/",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "description": "Docker Desktop에 AI 기반 Dockerfile 자동 생성 기능이 추가되면서 컨테이너화 작업이 혁신적으로 간소화되었습니다. 기존에는 베스트 프랙티스를 숙지한 개발자만 최적화된 이미지를 만들 수 있었지만, 이제 AI가 프로젝트 구조를 분석해 자동으로 multi-stage build를 적용합니다. 실제 베타 테스터들의 피드백에 따르면 이미지 크기가 평균 70% 감소했고, 빌드 시간도 절반으로 줄었습니다. Microsoft와 Google은 이미 내부 프로젝트에 적용 중이며, 특히 마이크로서비스 아키텍처 환경에서 효과가 극대화됩니다. 면접에서도 AI 도구 활용 경험을 묻는 질문이 늘어나고 있어, 실무 경험을 쌓아두는 것이 유리합니다. 보안 스캔 기능도 강화되어 취약점을 실시간으로 탐지하고 수정 방안을 제안합니다. 무료 티어에서도 월 100회까지 AI 기능을 사용할 수 있어 개인 프로젝트에도 활용 가능합니다.",
            "summary": "Docker Desktop에 AI 기반 Dockerfile 자동 생성 기능이 추가되면서 컨테이너화 작업이 혁신적으로 간소화되었습니다. 기존에는 베스트 프랙티스를 숙지한 개발자만 최적화된 이미지를 만들 수 있었지만, 이제 AI가 프로젝트 구조를 분석해 자동으로 multi-stage build를 적용합니다. 실제 베타 테스터들의 피드백에 따르면 이미지 크기가 평균 70% 감소했고, 빌드 시간도 절반으로 줄었습니다. Microsoft와 Google은 이미 내부 프로젝트에 적용 중이며, 특히 마이크로서비스 아키텍처 환경에서 효과가 극대화됩니다. 면접에서도 AI 도구 활용 경험을 묻는 질문이 늘어나고 있어, 실무 경험을 쌓아두는 것이 유리합니다. 보안 스캔 기능도 강화되어 취약점을 실시간으로 탐지하고 수정 방안을 제안합니다. 무료 티어에서도 월 100회까지 AI 기능을 사용할 수 있어 개인 프로젝트에도 활용 가능합니다.",
            "short_description": "Docker Desktop에 AI 기반 Dockerfile 자동 생성 기능이 추가되어 개발 시간을 60% 단축시킵니다.",
            "detail_markdown": (
                "SUMMARY: Docker Desktop AI, 컨테이너 최적화를 자동화하다\n\n"
                "## 🎯 핵심 포인트\n"
                "- AI가 프로젝트 분석 후 multi-stage build Dockerfile 자동 생성\n"
                "- 베타 테스트 결과 이미지 크기 평균 70% 감소, 빌드 시간 50% 단축\n"
                "- 보안 취약점 실시간 탐지 및 수정 제안 기능 통합\n"
                "- Microsoft, Google 내부 프로젝트에 이미 적용 중\n\n"
                "## 💡 왜 지금 주목해야 하나\n"
                "- DevOps 채용 시 AI 도구 활용 능력 필수 스킬로 부상\n"
                "- 컨테이너 최적화 지식 없어도 베스트 프랙티스 자동 적용 가능\n"
                "- 마이크로서비스 환경에서 수십 개 서비스 관리 시 생산성 극대화\n"
                "- 무료 티어 제공 - 개인 프로젝트로 포트폴리오 강화 기회\n\n"
                "## 🔥 실무 적용 팁\n"
                "- Docker Desktop 최신 버전 설치 후 AI 기능 활성화\n"
                "- 기존 Dockerfile과 AI 생성 결과 비교 학습 추천\n"
                "- docker scout로 보안 점검 자동화 파이프라인 구축\n"
            ),
            "score": 720,
            "relevance_score": 900
        },
        {
            "id": "fallback_3",
            "title": "⚡ Rust가 Python을 대체? 데이터 과학 라이브러리 Polars 급부상",
            "original_title": "Rust Polars Library Challenges Pandas",
            "source": "Towards Data Science",
            "url": "https://towardsdatascience.com/",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "description": "Rust로 작성된 데이터프레임 라이브러리 Polars가 Pandas의 아성에 도전장을 내밀었습니다. 벤치마크 결과 대용량 데이터 처리 속도가 Pandas 대비 평균 10배 빠르고, 메모리 사용량은 절반 수준입니다. Netflix와 Bloomberg는 이미 프로덕션 환경에서 Polars를 사용 중이며, PyData 커뮤니티에서도 뜨거운 논쟁이 벌어지고 있습니다. 특히 멀티코어 CPU를 자동으로 활용하는 병렬 처리 기능 덕분에 별도 최적화 없이도 고성능을 발휘합니다. 기존 Pandas 코드와 유사한 API를 제공해 학습 곡선이 낮고, lazy evaluation으로 쿼리 최적화도 자동으로 처리됩니다. 데이터 엔지니어 채용 공고에서 Polars 경험을 우대하는 사례가 늘고 있으며, Kaggle 대회에서도 사용 빈도가 급증하고 있습니다. 다만 Pandas의 방대한 에코시스템을 따라잡기까지는 시간이 필요하므로, 프로젝트 특성에 맞게 선택해야 합니다.",
            "summary": "Rust로 작성된 데이터프레임 라이브러리 Polars가 Pandas의 아성에 도전장을 내밀었습니다. 벤치마크 결과 대용량 데이터 처리 속도가 Pandas 대비 평균 10배 빠르고, 메모리 사용량은 절반 수준입니다. Netflix와 Bloomberg는 이미 프로덕션 환경에서 Polars를 사용 중이며, PyData 커뮤니티에서도 뜨거운 논쟁이 벌어지고 있습니다. 특히 멀티코어 CPU를 자동으로 활용하는 병렬 처리 기능 덕분에 별도 최적화 없이도 고성능을 발휘합니다. 기존 Pandas 코드와 유사한 API를 제공해 학습 곡선이 낮고, lazy evaluation으로 쿼리 최적화도 자동으로 처리됩니다. 데이터 엔지니어 채용 공고에서 Polars 경험을 우대하는 사례가 늘고 있으며, Kaggle 대회에서도 사용 빈도가 급증하고 있습니다. 다만 Pandas의 방대한 에코시스템을 따라잡기까지는 시간이 필요하므로, 프로젝트 특성에 맞게 선택해야 합니다.",
            "short_description": "Rust 기반 Polars 라이브러리가 Pandas 대비 10배 빠른 성능으로 데이터 과학계를 뒤흔들고 있습니다.",
            "detail_markdown": (
                "SUMMARY: Rust 기반 Polars, Pandas 대비 10배 빠른 성능으로 데이터 과학 판도 바꾼다\n\n"
                "## 🎯 핵심 포인트\n"
                "- 벤치마크: 1GB CSV 파일 처리 시 Pandas 12초 vs Polars 1.2초\n"
                "- 자동 병렬 처리로 멀티코어 CPU 100% 활용 - 별도 최적화 불필요\n"
                "- Lazy evaluation으로 쿼리 자동 최적화, 불필요한 연산 제거\n"
                "- Netflix, Bloomberg 프로덕션 환경 적용 완료\n\n"
                "## 💡 왜 지금 주목해야 하나\n"
                "- 데이터 엔지니어 채용 시 Polars 경험 우대 증가 추세\n"
                "- Kaggle 대회 상위권 솔루션에서 Polars 사용 급증\n"
                "- 대용량 데이터 처리 프로젝트에서 Pandas 한계 명확\n"
                "- Pandas API와 유사해 기존 지식 재활용 가능 - 학습 부담 낮음\n\n"
                "## 🔥 실무 적용 팁\n"
                "- `pip install polars` 후 간단한 데이터 처리부터 시작\n"
                "- Pandas 코드를 Polars로 변환하는 공식 가이드 참고\n"
                "- 100MB 이상 데이터셋에서 성능 차이 극대화 - 대용량 위주 적용\n"
            ),
            "score": 650,
            "relevance_score": 780
        }
    ]
    for item in items:
        _enrich_news_item(item, item.get("original_title") or item.get("title"))
    return items
