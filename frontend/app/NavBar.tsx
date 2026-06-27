'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function NavBar() {
  const pathname = usePathname();
  return (
    <header className="topNav">
      <Link className="brand" href="/dashboard">
        <span className="brandIcon">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="1" y="7" width="3" height="6" rx="1" fill="white" opacity=".7" />
            <rect x="5.5" y="4" width="3" height="9" rx="1" fill="white" opacity=".85" />
            <rect x="10" y="1" width="3" height="12" rx="1" fill="white" />
          </svg>
        </span>
        App Review Analyze
      </Link>
      <nav>
        <Link href="/dashboard" className={pathname === '/dashboard' ? 'active' : ''}>
          Dashboard
        </Link>
        <Link href="/reviews" className={pathname === '/reviews' ? 'active' : ''}>
          Reviews
        </Link>
        <Link href="/data-operations" className={pathname === '/data-operations' ? 'active' : ''}>
          데이터 운영 현황
        </Link>
        <Link href="/rating-trends" className={pathname === '/rating-trends' ? 'active' : ''}>
          앱 평점 추이 분석
        </Link>
        <Link href="/reports" className={pathname === '/reports' ? 'active' : ''}>
          AI 리포트
        </Link>
        <Link href="/compare" className={pathname === '/compare' ? 'active' : ''}>
          경쟁사 비교
        </Link>
      </nav>
    </header>
  );
}
