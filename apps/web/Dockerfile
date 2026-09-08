FROM node:20-slim

WORKDIR /app

# Copy application source including node_modules
COPY . .

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["npm", "run", "dev"]
