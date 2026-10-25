# Optional: host the built React app on a private S3 bucket behind CloudFront (HTTPS, no public bucket).
# Build first: (cd frontend && npm run build). Enable with -var enable_frontend_hosting=true.

locals {
  frontend_dist = "${path.module}/../../frontend/dist"
  mime_types = {
    html = "text/html"
    js   = "application/javascript"
    css  = "text/css"
    svg  = "image/svg+xml"
    json = "application/json"
    png  = "image/png"
    ico  = "image/x-icon"
    map  = "application/json"
  }
  frontend_files = var.enable_frontend_hosting ? toset([for f in fileset(local.frontend_dist, "**") : f if f != "config.js"]) : toset([])
}

resource "aws_s3_bucket" "frontend" {
  count         = var.enable_frontend_hosting ? 1 : 0
  bucket_prefix = "costwarden-web-"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  count                   = var.enable_frontend_hosting ? 1 : 0
  bucket                  = aws_s3_bucket.frontend[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cloudfront_origin_access_control" "frontend" {
  count                             = var.enable_frontend_hosting ? 1 : 0
  name                              = "costwarden-web"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "frontend" {
  count               = var.enable_frontend_hosting ? 1 : 0
  enabled             = true
  default_root_object = "index.html"
  price_class         = "PriceClass_100"

  origin {
    domain_name              = aws_s3_bucket.frontend[0].bucket_regional_domain_name
    origin_id                = "web"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend[0].id
  }

  default_cache_behavior {
    target_origin_id       = "web"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    # AWS managed policy: CachingOptimized
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  }

  # Single-page app: unknown paths serve index.html
  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }

  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

data "aws_iam_policy_document" "frontend" {
  count = var.enable_frontend_hosting ? 1 : 0

  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.frontend[0].arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.frontend[0].arn]
    }
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  count  = var.enable_frontend_hosting ? 1 : 0
  bucket = aws_s3_bucket.frontend[0].id
  policy = data.aws_iam_policy_document.frontend[0].json
}

resource "aws_s3_object" "frontend" {
  for_each     = local.frontend_files
  bucket       = aws_s3_bucket.frontend[0].id
  key          = each.value
  source       = "${local.frontend_dist}/${each.value}"
  etag         = filemd5("${local.frontend_dist}/${each.value}")
  content_type = lookup(local.mime_types, element(reverse(split(".", each.value)), 0), "application/octet-stream")
}

# Runtime config: tells the hosted app where the API is. The API key is never written here;
# users enter it in the app's Settings.
resource "aws_s3_object" "frontend_config" {
  count        = var.enable_frontend_hosting ? 1 : 0
  bucket       = aws_s3_bucket.frontend[0].id
  key          = "config.js"
  content      = "window.__CW__ = { apiUrl: ${jsonencode(trimsuffix(aws_lambda_function_url.api.function_url, "/"))} }\n"
  content_type = "application/javascript"
}
