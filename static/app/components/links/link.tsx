import {forwardRef, useContext} from 'react';
import {Link as RouterLink} from 'react-router';
import styled from '@emotion/styled';
import {Location, LocationDescriptor} from 'history';

import {RouteContext} from 'sentry/utils/routeContext';
import {normalizeUrl} from 'sentry/utils/withDomainRequired';

import {linkStyles} from './styles';

export interface LinkProps
  extends Omit<
    React.DetailedHTMLProps<React.HTMLAttributes<HTMLAnchorElement>, HTMLAnchorElement>,
    'href' | 'target' | 'as' | 'css'
  > {
  /**
   * The string path or LocationDescriptor object
   */
  to: ((location: Location) => LocationDescriptor) | LocationDescriptor;
  /**
   * Style applied to the component's root
   */
  className?: string;
  /**
   * Indicator if the link should be disabled
   */
  disabled?: boolean;
  /**
   * Forwarded ref
   */
  forwardedRef?: React.Ref<HTMLAnchorElement>;
}

/**
 * A context-aware version of Link (from react-router) that falls
 * back to <a> if there is no router present
 */
function BaseLink({disabled, to, forwardedRef, ...props}: LinkProps): React.ReactElement {
  const route = useContext(RouteContext);
  const location = route?.location;
  to = normalizeUrl(to, location);

  if (!disabled && location) {
    return <RouterLink to={to} ref={forwardedRef as any} {...props} />;
  }

  return <a href={typeof to === 'string' ? to : ''} ref={forwardedRef} {...props} />;
}

// Re-assign to Link to make auto-importing smarter
const Link = styled(
  forwardRef<HTMLAnchorElement, Omit<LinkProps, 'forwardedRef'>>((props, ref) => (
    <BaseLink forwardedRef={ref} {...props} />
  ))
)`
  ${linkStyles}
`;

export default Link;
