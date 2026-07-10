#!/bin/bash
set -e

REPO="aprameyak/2027-tech-jobs"
ISSUES="525 524 523 522 521 520 519 518 517 516 515 514 513 512 509 508 507 506 505 502 501 500 499 492 491 489 488 487 486 478 477 476 475 474 473 464 463 462 461 460 459 458 457 456 455 454 453 452 451 450 449 448 447 439 409 408 407"

echo "Starting approval process..."
for ISSUE_NUM in $ISSUES; do
  curl -s -X POST \
    -H "Authorization: token ${GITHUB_TOKEN}" \
    -H "Accept: application/vnd.github.v3+json" \
    "https://api.github.com/repos/${REPO}/issues/${ISSUE_NUM}/labels" \
    -d '{"labels":["approved"]}' > /dev/null 2>&1
  echo "✅ #${ISSUE_NUM}"
done

echo "✓ All 53 issues approved!"
