type Props = {
  size?: 'sm' | 'md' | 'lg';
  variant?: 'full' | 'icon' | 'wordmark' | 'white';
  className?: string;
  href?: string;
  onClick?: () => void;
};

const heightMap = {
  sm: '28px',
  md: '36px',
  lg: '48px',
};

export function StudyRewindLogo({ size = 'md', variant = 'full', className = '', href, onClick }: Props) {
  const h = heightMap[size];
  const isWhite = variant === 'white';
  const defaultHref = typeof window !== 'undefined' && localStorage.getItem('token') ? '#/dashboard' : '#/';
  const targetHref = href || defaultHref;

  return (
    <a
      className={`brand logo-${size} ${className}`}
      href={targetHref}
      onClick={onClick}
      aria-label="StudyRewind home"
      style={{ display: 'inline-flex', alignItems: 'center', textDecoration: 'none' }}
    >
      <img
        src="/logo.png"
        alt="StudyRewind Logo"
        style={{
          height: h,
          width: 'auto',
          objectFit: 'contain',
          filter: isWhite ? 'brightness(0) invert(1)' : 'none',
        }}
      />
    </a>
  );
}
